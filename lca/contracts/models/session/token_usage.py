"""TokenUsage TypedDict for the run session writer Protocol.

Wire-shape token counters carried on ``surface/assistant_message``. Distinct
from :class:`lca.contracts.models.core.conversation.llm.TokenUsage` (the
provider response shape); this is the persisted-journal projection.
"""

from __future__ import annotations

from typing import TypedDict


class TokenUsage(TypedDict, total=False):
    """Persisted token counters. All fields optional — providers vary."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


__all__ = ["TokenUsage"]
