"""Bounded prior-turn extraction from LobeHub OpenAI messages."""

from __future__ import annotations

from typing import Any

from gateway.lobehub_bridge.constants import MAX_HISTORY_CHARS, MAX_HISTORY_MESSAGES
from lca.contracts.models.core.conversation import ConversationTurn


def extract_prior_turns(messages: list[Any], *, plain_text_fn: Any) -> tuple[ConversationTurn, ...]:
    """Prior user/assistant turns before the last user message (native messages[] slice)."""
    turns: list[ConversationTurn] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue
        text = plain_text_fn(item.get("content"))
        if not text:
            continue
        turns.append(ConversationTurn(role=role, content=text))

    if len(turns) <= 1:
        return ()

    if turns and turns[-1].role == "user":
        turns = turns[:-1]

    if not turns:
        return ()

    selected = turns[-MAX_HISTORY_MESSAGES:]
    return tuple(_truncate_turns_to_budget(selected, MAX_HISTORY_CHARS))


def _truncate_turns_to_budget(
    turns: list[ConversationTurn], max_chars: int
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
