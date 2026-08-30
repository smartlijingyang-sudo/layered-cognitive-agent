"""Select compact conversation history from an OpenAI-style messages payload."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.models.core.conversation import ConversationTurn

MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARS = 6000


PlainTextExtractor = Callable[[Any], str]


def extract_prior_turns(
    messages: list[Any],
    *,
    plain_text_fn: PlainTextExtractor,
) -> tuple[ConversationTurn, ...]:
    """Return compact user/assistant context before the latest user message."""
    turns: list[ConversationTurn] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue
        text = plain_text_fn(item.get("content"))
        if text:
            turns.append(ConversationTurn(role=role, content=text))
    if len(turns) <= 1:
        return ()
    if turns[-1].role == "user":
        turns = turns[:-1]
    if not turns:
        return ()
    return tuple(truncate_turns_to_budget(turns[-MAX_HISTORY_MESSAGES:], MAX_HISTORY_CHARS))


def truncate_turns_to_budget(
    turns: list[ConversationTurn],
    max_chars: int,
) -> list[ConversationTurn]:
    """Keep the most recent turns within a total character budget."""
    if max_chars <= 0:
        return []
    kept: list[ConversationTurn] = []
    used = 0
    for turn in reversed(turns):
        content = turn.content
        if len(content) > max_chars:
            content = "…" + content[-max_chars:]
        need = len(content) + (2 if kept else 0)
        if used + need > max_chars and kept:
            break
        kept.append(ConversationTurn(role=turn.role, content=content))
        used += need
    kept.reverse()
    return kept


__all__ = [
    "MAX_HISTORY_CHARS",
    "MAX_HISTORY_MESSAGES",
    "PlainTextExtractor",
    "extract_prior_turns",
    "truncate_turns_to_budget",
]
