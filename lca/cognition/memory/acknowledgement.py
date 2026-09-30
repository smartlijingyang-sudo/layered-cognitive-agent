"""User-visible memory claims follow a disk receipt.

The model may say a fact was remembered only after the curated projection
receipt says the write landed. This check is pure. Callers pass the draft
and the flag the memory graph node already stamped.
"""

from __future__ import annotations

import re

_CLAIM = re.compile(r"已记下|已记住|我记住了|I(?:'ve| have) (?:noted|remembered)", re.IGNORECASE)
_REFUSAL = "这条还没有写入记忆文件。我不能说已经记下。"


def guard_memory_claim(text: str, *, allowed: bool) -> str:
    """Return ``text`` unchanged, or a refusal when it claims a missing write."""

    if allowed or not text or _CLAIM.search(text) is None:
        return text
    return _REFUSAL


__all__ = ["guard_memory_claim"]
