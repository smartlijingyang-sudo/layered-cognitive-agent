"""Multi-turn conversation fragments for agent prompts (LobeHub messages[] parity)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationTurn:
    """One OpenAI-style chat turn (user or assistant prose only)."""

    role: str
    content: str
