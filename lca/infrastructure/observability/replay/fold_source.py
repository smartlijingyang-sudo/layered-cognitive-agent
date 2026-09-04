"""ModelVisibleFoldSource —— 从 ``<run_id>.spine.jsonl`` 重建 model-visible。

ADR-0185 §3.4 + §3.7:viewer 反查 model-visible 走 ``foldRequestHeader``
fold 重建,spine.jsonl 为唯一 SSOT（I-FW-SSOT-1 + I-MV-2）。

设计:

- 纯只读;不写盘;不调 LLM / tool
- 走 :class:`lca_kernel.events.fold.foldRequestHeader` 离线 fold
- 输入 = run_dir + run_id + step_id,输出 = 重建的 ``(header, messages,
  tool_schemas, manifest, source, digest_verified)``
- spine 文件缺失 / 无 model-visible 事件 → 返回 ``None``(caller 退化为
  journal 推导)

ADR-0185 PR-4 收口:旧 ``<run_dir>/model_visible/`` 旁路读取已删除,
本模块是唯一 model-visible viewer 重建入口。
"""

from __future__ import annotations

import hashlib
import json
import logging
import typing as _typing
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca_kernel.events.fold import (
    EpochHeader,
    foldRequestHeader,
)
from lca_kernel.events.payloads_model_visible import (
    SpineLlmRequestHeaderAssistantPayload,
    SpineLlmRequestHeaderPayload,
)
from lca_kernel.events.reader import SpineReader
from lca_kernel.events.spine_runtime import SpineEventRecord

_log = logging.getLogger(__name__)

# Pydantic forward-ref rebuild:对齐 :mod:`lca.plugins.events.hooks.model_visible.hook`
# 的 `_rebuild_ns` 处理。``AssistantRequestConfig`` / ``ToolCallDict`` 等
# forward-ref 在 PR-0 stub 为 ``Any``;pydantic v2 默认不自动 rebuild,
# 这里显式 force-rebuild 一次,保证 ``model_validate`` 不抛
# ``class-not-fully-defined``(双模块各自 import 时的副作用)。
_rebuild_ns = {
    "AssistantRequestConfig": _typing.Any,
    "MessageDict": _typing.Any,
    "ToolCallDict": _typing.Any,
    "UsageDict": _typing.Any,
}
for _payload_cls in (
    SpineLlmRequestHeaderPayload,
    SpineLlmRequestHeaderAssistantPayload,
):
    try:
        _payload_cls.model_rebuild(force=True, _types_namespace=_rebuild_ns)
    except Exception as exc:  # INTENTIONAL: rebuild 失败仅记日志;主路径不挡
        _log.debug("fold_source: payload_model_rebuild_skip: %s", exc)
del _payload_cls, _rebuild_ns, _typing


@dataclass(frozen=True)
class FoldedModelVisible:
    """``foldRequestHeader`` + assistant payload fold 后的 viewer 输入。

    与 :class:`lca.contracts.observability.replay.StepContextAt` 字段对齐
    (避免 caller 二次映射),但保持纯 immutable dataclass 以便测试。

    字段语义:

    - ``header`` —— :class:`EpochHeader` fold 结果;``None`` 表无 fold
      事件流(旧 run / 未接 PR-2 publisher)。
    - ``messages`` / ``tool_schemas`` / ``manifest`` —— 从最近一条
      ``spine.llm.request.header`` payload 提取的原文,用于 viewer
      渲染;空 tuple / 空 dict 表 fold header 存在但字段缺省。
    - ``assistant`` —— 同 ``(run_id, step_id)`` 的最近
      ``spine.llm.request.header.assistant`` payload;``None`` 表无对应
      事件(post hook 未跑 / 跳过)。
    - ``header_digest`` —— :func:`_canonical_digest` 字节级 sha256
      摘要;``""`` 表无 fold。
    - ``source`` —— 标记 fold 路径,常量化于
      :data:`SOURCE_FOLD`。
    - ``digest_verified`` —— :data:`True`(fold 路径默认真;
      fold 路径永远走 canonical = True)。
    """

    header: EpochHeader | None
    messages: tuple[Any, ...]
    tool_schemas: tuple[Any, ...]
    manifest: dict[str, Any] | None
    assistant: SpineLlmRequestHeaderAssistantPayload | None
    header_digest: str
    source: str
    digest_verified: bool


# 来源标记字符串;viewer 字符串比对走这个常量化值
SOURCE_FOLD: str = "replayed_fold"
"""fold 路径成功重建时的 :attr:`FoldedModelVisible.source` 值。"""


def _canonical_digest(header: EpochHeader) -> str:
    """``sha256:`` 前缀的 canonical header digest。

    对齐 :func:`lca.plugins.events.hooks.model_visible.hook._canonical_digest`
    算法;viewer 与 publisher 走同一摘要函数,保证 publisher ``previous_header_digest``
    与 viewer 算出的 digest 字节级相等(I-MV-2 守护)。
    """
    payload: dict[str, Any] = {
        "config": header.config,
        "adapter_defaults": header.adapter_defaults,
        "system": header.system,
        "tools": list(header.tools),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _iter_spine_records(spine_path: Path) -> Iterable[SpineEventRecord]:
    """走 :class:`SpineReader` 读 spine ledger 事件流;IO 失败 → 空 iter。

    SpineReader.events() 自身已容错(损坏行 skip + log),这里再包一层
    catch-all 防止 transport / JSONDecodeError 等泄漏到 caller。
    """
    try:
        # SpineReader 签名 = (run_id, *, path);run_id 必填(用于 default_path 解析
        # 与日志字段);这里取 spine 文件 stem 作为 run_id 占位(后续 caller
        # 不依赖该字段,SpineReader 仅作 typed reader 用)。
        reader = SpineReader(run_id=spine_path.stem, path=spine_path)
    except Exception as exc:  # INTENTIONAL: reader 构造失败 ≠ fold 失败
        _log.debug("fold_source: SpineReader 构造失败 (%s)", exc)
        return
    try:
        yield from reader.events()
    except Exception as exc:  # INTENTIONAL: best-effort fold
        _log.debug("fold_source: events() 抛错 (%s)", exc)
        return


def _load_request_header_payload(
    spine_path: Path,
    *,
    step_id: str,
) -> SpineLlmRequestHeaderPayload | None:
    """扫 spine 取该 step 最近一条 ``spine.llm.request.header`` payload。

    走 :class:`SpineEventRecord` 字节布局;fold 端用 :func:`foldRequestHeader`
    —— 本函数独立提取「最近一条原文 payload」用于 ``messages`` / ``tools``
    / ``manifest`` 投影。
    """
    latest: SpineLlmRequestHeaderPayload | None = None
    for record in _iter_spine_records(spine_path):
        if record.category != "spine.llm.request.header":
            continue
        payload_dict = record.payload if isinstance(record.payload, Mapping) else {}
        if payload_dict.get("step_id") != step_id:
            continue
        try:
            latest = SpineLlmRequestHeaderPayload.model_validate(dict(payload_dict))
        except Exception as exc:  # INTENTIONAL: payload 不合规 → skip
            _log.debug("fold_source: request_header payload 解析失败 (%s)", exc)
            continue
    return latest


def _load_assistant_payload(
    spine_path: Path,
    *,
    step_id: str,
) -> SpineLlmRequestHeaderAssistantPayload | None:
    """扫 spine 取该 step 最近一条 ``spine.llm.request.header.assistant``。

    返回 ``None`` 表无对应事件(透明降级;viewer 在 ``FoldedModelVisible.assistant``
    为 ``None`` 时跳过 assistant 投影)。
    """
    latest: SpineLlmRequestHeaderAssistantPayload | None = None
    for record in _iter_spine_records(spine_path):
        if record.category != "spine.llm.request.header.assistant":
            continue
        payload_dict = record.payload if isinstance(record.payload, Mapping) else {}
        if payload_dict.get("step_id") != step_id:
            continue
        try:
            latest = SpineLlmRequestHeaderAssistantPayload.model_validate(dict(payload_dict))
        except Exception as exc:  # INTENTIONAL: payload 不合规 → skip
            _log.debug("fold_source: assistant payload 解析失败 (%s)", exc)
            continue
    return latest


def fold_model_visible(
    *,
    run_dir: Path,
    run_id: str,
    step_id: str,
) -> FoldedModelVisible | None:
    """读 ``<run_dir>/<run_id>.spine.jsonl`` 重建该 step 的 model-visible。

    Args:
        run_dir: per-run 目录;spine ledger 落盘于此。
        run_id: 目标 run 标识;仅用于 ``spine_filename_for_run`` 路径解析。
        step_id: 目标 step_id;与 publisher publish 时的 step_id 形态一致
            (``step-NNN``,3 位零填充)。

    Returns:
        :class:`FoldedModelVisible` 重建结果;``None`` 表 spine 文件不存在
        或该 step_id 无 model-visible 事件流(caller 退化为 journal 推导)。

    失败语义:

    - spine ledger 不存在 → ``None``(``SpineReader.events()`` 不抛)
    - spine 存在但该 step_id 无 request/header 事件 → ``None``
    - 解析 payload 失败 → ``None``(skip + log)
    - 任一环节失败均不抛;best-effort fold

    时序:无副作用;不调 LLM / tool / bus;纯 IO + 纯函数 fold。

    所有权:本函数由 :class:`StandardCursor.at()` 调用;
    webserver / dashboard 调方同样走此 seam,是唯一 model-visible
    viewer 重建入口。
    """
    from lca.infrastructure.observability.spine.sinks.naming import (
        spine_filename_for_run,
    )

    spine_path = run_dir / spine_filename_for_run(run_id)
    if not spine_path.exists():
        return None

    header: EpochHeader | None = foldRequestHeader(
        _iter_spine_records(spine_path),
        step_id=step_id,
    )
    if header is None:
        return None

    header_payload = _load_request_header_payload(spine_path, step_id=step_id)
    assistant_payload = _load_assistant_payload(spine_path, step_id=step_id)

    messages: tuple[Any, ...] = tuple(header_payload.messages) if header_payload is not None else ()
    tool_schemas: tuple[Any, ...] = (
        tuple(header_payload.tools) if header_payload is not None else ()
    )
    manifest: dict[str, Any] | None
    if header_payload is not None and header_payload.manifest is not None:
        # ContextManifest 是 frozen dataclass;序列化走 ``dataclasses.asdict``
        # 拿原 dict 形态(typed items 序列化为 list;nested dataclass 也递归展开);
        # fold source 内部统一为 ``dict[str, Any]`` 暴露给 viewer。
        from dataclasses import asdict as _asdict

        dumped = _asdict(header_payload.manifest)
        manifest = dumped if isinstance(dumped, dict) else None
    else:
        manifest = None

    return FoldedModelVisible(
        header=header,
        messages=messages,
        tool_schemas=tool_schemas,
        manifest=manifest,
        assistant=assistant_payload,
        header_digest=_canonical_digest(header),
        source=SOURCE_FOLD,
        digest_verified=True,
    )


__all__ = [
    "SOURCE_FOLD",
    "FoldedModelVisible",
    "fold_model_visible",
]
