"""Format prior conversation turns for prompt templates (GeneralChatAgent parity)."""

from __future__ import annotations

from lca.contracts.models.core.conversation import ConversationTurn

_EMPTY_PRIOR = "(none)"


def format_prior_conversation(turns: tuple[ConversationTurn, ...] | list[ConversationTurn]) -> str:
    """Render bounded prior turns as role-labeled lines (no synthetic history blocks)."""
    if not turns:
        return _EMPTY_PRIOR
    lines: list[str] = []
    for turn in turns:
        role = (turn.role or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = (turn.content or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else _EMPTY_PRIOR
