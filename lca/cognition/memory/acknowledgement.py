"""User-visible memory claims follow a disk receipt.

The model may say a fact was remembered only after a successful curated
projection is still unspent. ``guard_memory_claim`` is pure. ``guard_reply``
spends that unspent copy when the draft claims the write.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from lca.infrastructure.memory.contextfiles.domain.curated import may_acknowledge_projection

_CLAIM = re.compile(
    r"已记下|已记住|我记住了|我记下了|已经记录|记下来了|记下了|帮你记下|"
    # run_45fa85c1ee75 实测漏网：未来式承诺同样是写盘宣称
    r"我[来先会]?记下|我.{0,6}记录下来|"
    r"I(?:'ve| have) (?:noted|remembered)",
    re.IGNORECASE,
)
_REFUSAL = "这条还没有写入记忆文件。我不能说已经记下。"


def _as_mapping(runtime: object) -> Mapping[str, Any] | None:
    """Return a Mapping view of runtime when it is dict-like, else None."""
    if isinstance(runtime, Mapping):
        return runtime
    return None


def guard_memory_claim(text: str, *, allowed: bool) -> str:
    """Return ``text`` unchanged, or a refusal when it claims a missing write."""

    if allowed or not text or _CLAIM.search(text) is None:
        return text
    return _REFUSAL


def guard_reply(text: str | None, runtime: object | None) -> str | None:
    """Spend one unspent successful projection, or fall back to an injected receipt.

    ADR-0260 §6 fail-closed: a draft that claims a memory write is allowed
    only with a spent claim right or an allowing receipt. With no memory
    subsystem and no injected receipt the claim is replaced by the refusal
    (previously fail-open: "我记下了" sailed through on memory-less runs,
    e.g. run_45fa85c1ee75).
    """

    if text is None or _CLAIM.search(text) is None:
        return text
    memory = getattr(runtime, "memory", None) if runtime is not None else None
    if memory is None and runtime is not None:
        runtime_mapping = _as_mapping(runtime)
        if runtime_mapping is not None:
            memory = runtime_mapping.get("memory")
    take = getattr(memory, "take_claim_right", None) if memory is not None else None
    if callable(take):
        return text if take() is not None else _REFUSAL
    receipt = getattr(runtime, "memory_receipt", None) if runtime is not None else None
    if receipt is None and runtime is not None:
        runtime_mapping = _as_mapping(runtime)
        if runtime_mapping is not None:
            receipt = runtime_mapping.get("memory_receipt")
    if receipt is None:
        return _REFUSAL
    allowed = getattr(receipt, "may_acknowledge", None)
    if allowed is None:
        allowed = may_acknowledge_projection(receipt)
    return guard_memory_claim(text, allowed=bool(allowed))


__all__ = ["guard_memory_claim", "guard_reply"]
