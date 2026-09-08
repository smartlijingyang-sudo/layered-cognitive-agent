"""Canonical payload digest —— ``sha256:<hex>`` of canonical JSON.

ADR-0203 §算法分类
------------------
``report_digest_inconsistency.md`` 调查了 40+ 处 digest 算点,梳理出 5 类
算法形态(详见 ADR-0203 §算法分类):

1. **full 64-hex + ``sha256:`` 前缀** —— 本模块覆盖的核心形态。
   由 canonical JSON 序列化后 sha256,字节级稳定。
2. **full 64-hex 无前缀** —— 局部用途(如 state_store、plan_proposal)。
3. **truncated 16/24/32 hex** —— 视觉/dedup 用,不参与跨模块比对。
4. **非 hash 标签字面量** —— ``f"tool:{name}"``,仅做语义标记。
5. **人类可读摘要字符串** —— ``_summarize_args`` 的输出。

本模块是 (1)(2)(3) 的统一 SSOT,提供 ``canonical_digest(payload, *, length, prefix, ensure_ascii)``
函数 + 历史兼容的 :func:`sha256_payload_digest` 别名。

约束
----
- 序列化参数固定 ``sort_keys=True, ensure_ascii=False(default), default=str``,
  与 ADR-0185 PR-4 收口时的字节级行为一致;非 ASCII 内容 digest
  不因 ``ensure_ascii`` 转义改变。
- ``length`` 必须为正整数且 ≤ 64;只截断 sha256 hex 字符串,不 padding。
- ``prefix`` 默认 ``"sha256:"``(ADR-0185 §2.5 wire form);
  空字符串表示无前缀。
- 不可变(pure):相同输入恒返回相同输出;无 I/O、无副作用。
- ``contracts`` 层约束:本模块**禁止**引入 I/O、logging、第三方依赖。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

DEFAULT_DIGEST_PREFIX: str = "sha256:"
"""Default digest 前缀;对 ``length=64`` 的 full digest 配套使用。"""

# 约定长度集合 —— 视觉/dedup/on-wire 三类用例的标准化值。
# ADR-0203 §算法分类:不在此集合的 ``length`` 仍可计算(只是无 cross-site
# 互操作性),这里仅用于文档化主流用法。
_CONVENTIONAL_HEX_LENGTHS: frozenset[int] = frozenset({12, 16, 24, 32, 64})


def canonical_digest(
    payload: Any,
    *,
    length: int = 16,
    prefix: str = DEFAULT_DIGEST_PREFIX,
    ensure_ascii: bool = False,
) -> str:
    """``f"{prefix}{sha256(canonical_json(payload)).hexdigest()[:length]}"``。

    Parameters
    ----------
    payload:
        任意可被 ``json.dumps(..., default=str)`` 序列化的对象
        (dict / list / str / int / float / bool / None / dataclass / 自定义类)。
        默认 ``default=str`` 兜住非原生类型(datetime / Path / Enum 等)。
    length:
        保留的 hex 字符数;必须为正整数且 ≤ 64(默认值 16,匹配最常见
        trace id / step id 用例)。``12 / 16 / 24 / 32 / 64`` 为约定长度。
    prefix:
        拼接到 hex 前的前缀字符串(默认 ``"sha256:"`` per ADR-0185 §2.5
        wire form)。传空字符串表示无前缀。
    ensure_ascii:
        透传给 ``json.dumps``(默认 ``False``,与 loop-cursor adapter
        历史行为一致 —— 非 ASCII 字节级稳定)。

    Returns
    -------
    str:
        ``f"{prefix}{hex[:length]}"``,总长 = ``len(prefix) + length``。

    Raises
    ------
    ValueError:
        ``length`` 不是正整数或 > 64。
    """
    if not isinstance(length, int) or length <= 0 or length > 64:
        raise ValueError(f"length must be a positive integer ≤ 64, got {length!r}")
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=ensure_ascii,
        default=str,
    ).encode("utf-8")
    hex_digest = hashlib.sha256(encoded).hexdigest()[:length]
    return f"{prefix}{hex_digest}"


def sha256_payload_digest(payload: Any) -> str:
    """``sha256:<hex>`` 形式的 canonical payload digest(全 64 hex)。

    历史兼容别名:等同于 ``canonical_digest(payload, length=64, prefix="sha256:")``。
    用于 :class:`lca.cognition.brain.reasoner.reasoner.PromptReasoner`
    等路径依赖 64-hex 全长度 digest 的现有 caller(无需修改调用代码)。

    算法
    ----
    1. ``json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)``
       → UTF-8 字节序列。
    2. ``hashlib.sha256(...).hexdigest()`` → 64 hex 字符。
    3. 拼接 ``"sha256:"`` 前缀。

    返回
    ----
    ``str`` —— 形如 ``"sha256:abcd1234..."``(总长 71 字符)。
    """
    return canonical_digest(
        payload,
        length=64,
        prefix=DEFAULT_DIGEST_PREFIX,
        ensure_ascii=False,
    )


# 向后兼容的命名:DIGEST_PREFIX 是早期 PR-C 前时代的常量名,保留供
# 任何 import 这个常量的代码使用。
DIGEST_PREFIX: str = DEFAULT_DIGEST_PREFIX

__all__ = [
    "DEFAULT_DIGEST_PREFIX",
    "DIGEST_PREFIX",
    "canonical_digest",
    "sha256_payload_digest",
]
