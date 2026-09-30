"""Fold 输出投影:canonical 结果类型 + 归一 / 判等 helper。

fold core 返回的每个值都是投影(可缓存可重建,不得反向写事实):

- :class:`EpochHeader` —— header fold 的 canonical 投影
- :class:`StepTree` / :class:`TurnEntry` / :class:`StepEntry` —— step-tree 投影
- :class:`SurfaceFoldResult` / :class:`SurfaceFoldReplacement` —— surface 投影
- :func:`canonicalHeader` / :func:`headerEquals` —— 投影的归一与字节级判等

本模块不依赖 fold core / inputs,只定义结果形态。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class EpochHeader:
    """单次 LLM 调用的有效 header(对齐 dsh ``EpochHeader``)。

    字段语义对齐 dsh ``packages/core/session/src/types.ts`` ``EpochHeader``
    形态:

    - ``config`` — call config(provider / model / reasoning_effort / 采样标量)
    - ``adapter_defaults`` — adapter 实体化的有效字段标记
      (``reasoning_effort`` / ``max_tokens`` 哪几个由 adapter 决定)
    - ``system`` — 渲染后的 system prompt 原文;空字符串归一为 absent
    - ``tools`` — 装配的工具 schema 序列;空序列归一为 absent

    四字段均允许 ``None`` / 空,语义由 :func:`canonicalHeader` 归一化后单点表示
    决定。frozen + slots 保证 ``headerEquals`` / ``fold`` 不被原地改污染。
    """

    config: Mapping[str, Any] | None = None
    adapter_defaults: Mapping[str, Any] | None = None
    system: str | None = None
    tools: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)


def canonicalHeader(header: EpochHeader) -> EpochHeader:  # noqa: N802 (dsh parity)
    """归一 ``EpochHeader`` 到 canonical 形态(对齐 dsh ``canonicalHeader``)。

    规则:

    - 空字符串 ``system`` → ``None``
    - 空 ``tools`` 序列 → ``()``
    - ``config`` 永远保留(无空判定:``config`` 是 header 的最小可识别单元)
    - ``adapter_defaults`` 仅在 ``reasoning_effort == True`` 或
      ``max_tokens == True`` 时保留;否则 absent(对齐 dsh
      ``canonicalHeader`` spread 行为)

    返回新对象,不修改入参;``frozen`` 语义保证 caller 持有引用不变。
    """
    system = header.system if header.system else None
    tools = header.tools if header.tools else ()

    adapter_defaults_raw = header.adapter_defaults
    if adapter_defaults_raw and (
        adapter_defaults_raw.get("reasoning_effort") is True
        or adapter_defaults_raw.get("max_tokens") is True
    ):
        adapter_defaults: Mapping[str, Any] | None = adapter_defaults_raw
    else:
        adapter_defaults = None

    return EpochHeader(
        config=header.config,
        adapter_defaults=adapter_defaults,
        system=system,
        tools=tools,
    )


def _sameSchema(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:  # noqa: N802 (dsh parity)
    """工具 schema 字节级判等(对齐 dsh ``sameSchema``)。

    用 ``json.dumps(..., sort_keys=True)`` 做 canonical JSON 字符串比对;
    同一工具经同一路径装配,字段名顺序漂移不影响比对结果。
    """
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def headerEquals(a: EpochHeader, b: EpochHeader) -> bool:  # noqa: N802 (dsh parity)
    """canonical header 字段级判等(对齐 dsh ``headerEquals``)。

    逐字段比对:

    - ``config`` — 逐键比对(provider / model / reasoning_effort / temperature /
      max_tokens / stop 等),stop 列表元素逐一对位
    - ``adapter_defaults`` — ``reasoning_effort`` / ``max_tokens`` 标记位比对
    - ``system`` — 字符串严格等
    - ``tools`` — 长度等 + 元素顺序敏感 + 元素级 ``_sameSchema`` 字节级比对

    入参未归一时返回值仍正确(短字段按 ``None`` / 空 tuple 对位);但生产
    调用方应先 ``canonicalHeader`` 再比,与 dsh 实现一致。
    """
    if a.config != b.config:
        return False
    if a.adapter_defaults != b.adapter_defaults:
        return False
    if a.system != b.system:
        return False
    at = a.tools or ()
    bt = b.tools or ()
    if len(at) != len(bt):
        return False
    return all(_sameSchema(left, right) for left, right in zip(at, bt, strict=True))


# ── StepTree fold(对齐 DSH turn/step 事件重建)────────────────────────


@dataclass(frozen=True, slots=True)
class StepEntry:
    """单个 step 的折叠结果。

    - ``step`` —— step 序号(在 turn 内从 0 递增)
    - ``started`` —— 是否见过 ``step/start``
    - ``ended`` —— 是否见过 ``step/end``
    """

    step: int
    started: bool = False
    ended: bool = False


@dataclass(frozen=True, slots=True)
class TurnEntry:
    """单个 turn 的折叠结果。

    - ``turn`` —— turn 序号
    - ``started`` —— 是否见过 ``turn/start``
    - ``ended`` —— 是否见过 ``turn/end``
    - ``steps`` —— 该 turn 下已见过的 step(按 step 序号排序)
    """

    turn: int
    started: bool = False
    ended: bool = False
    steps: tuple[StepEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class StepTree:
    """事件流折叠出的 turn/step 树(对齐 DSH SessionEventMap turn/step 语义)。

    - ``turns`` —— 按 turn 序号排序的 turn 条目序列
    - ``active_turn`` —— 最近 ``turn/start`` 且未 ``turn/end`` 的 turn 序号;
      无活跃 turn 时为 None
    - ``active_step`` —— 最近 ``step/start`` 且未 ``step/end`` 的 (turn, step)
      对;无活跃 step 时为 None

    frozen + slots 保证 fold 结果不被原地改;每次 fold 返回新实例。
    """

    turns: tuple[TurnEntry, ...] = ()
    active_turn: int | None = None
    active_step: tuple[int, int] | None = None


# ── Surface fold(对齐 DSH foldSurface;ADR-0186 I-SESSION-2)────────────


@dataclass(frozen=True, slots=True)
class SurfaceFoldReplacement:
    """fold 过程中观察到的一次 replace。

    - ``seq`` — 替换节点自身的 log seq
    - ``start`` / ``end`` — 声明的被替换区间(含端点)
    - ``shadowed_seqs`` — 实际从 surface 摘掉的节点,surface 顺序
    """

    seq: int
    start: int
    end: int
    shadowed_seqs: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SurfaceFoldResult:
    """``foldSurface`` 的完整结果。

    - ``nodes`` — 当前模型可见 surface 的 seq,顺序即模型可见顺序
    - ``replacements`` — 按事件顺序记录的 replace;空 tuple 表示从未替换
    """

    nodes: tuple[int, ...]
    replacements: tuple[SurfaceFoldReplacement, ...] = ()
