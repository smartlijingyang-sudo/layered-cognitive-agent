"""User-visible memory claims follow a disk receipt.

The model may say a fact was remembered only after a successful curated
projection is still unspent. ``guard_memory_claim`` is pure. ``guard_reply``
spends that unspent copy when the draft claims the write.
"""

from __future__ import annotations

import re

from lca.infrastructure.memory.contextfiles.domain.curated import may_acknowledge_projection

_CLAIM = re.compile(r"已记下|已记住|我记住了|I(?:'ve| have) (?:noted|remembered)", re.IGNORECASE)
_REFUSAL = "这条还没有写入记忆文件。我不能说已经记下。"


def guard_memory_claim(text: str, *, allowed: bool) -> str:
    """Return ``text`` unchanged, or a refusal when it claims a missing write."""

    if allowed or not text or _CLAIM.search(text) is None:
        return text
    return _REFUSAL


def guard_reply(text: str | None, runtime: object | None) -> str | None:
    """Spend one unspent successful projection, or fall back to an injected receipt."""

    memory = getattr(runtime, "memory", None) if runtime is not None else None
    if memory is None and runtime is not None and hasattr(runtime, "get"):
        memory = runtime.get("memory")
    take = getattr(memory, "take_claim_right", None) if memory is not None else None
    if callable(take):
        if text is None or _CLAIM.search(text) is None:
            return text
        if take() is None:
            return _REFUSAL
        return text
    receipt = getattr(runtime, "memory_receipt", None) if runtime is not None else None
    if receipt is None and runtime is not None and hasattr(runtime, "get"):
        receipt = runtime.get("memory_receipt")
    if receipt is None or text is None:
        return text
    allowed = getattr(receipt, "may_acknowledge", None)
    if allowed is None:
        allowed = may_acknowledge_projection(receipt)
    return guard_memory_claim(text, allowed=bool(allowed))


__all__ = ["guard_memory_claim", "guard_reply"]
