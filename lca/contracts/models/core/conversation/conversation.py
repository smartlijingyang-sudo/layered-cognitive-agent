"""Multi-turn conversation fragments for agent prompts (LobeHub messages[] parity)."""

from __future__ import annotations

from dataclasses import dataclass

# Working-memory key: prior turns seeded from gateway / RunContext.extra.
PRIOR_CONVERSATION_WM_KEY = "prior_conversation"


@dataclass(frozen=True)
class ConversationTurn:
    """One OpenAI-style chat turn (user or assistant prose only)."""

    role: str
    content: str
