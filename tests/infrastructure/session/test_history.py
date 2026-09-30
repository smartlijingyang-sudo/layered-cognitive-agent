"""Tests for the LLM-turn history derivation seam.

``derive_turn_history`` is the infrastructure seam that keeps cognition from
importing the concrete runtime ``RunSessionWriter``.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.session.message import Message
from lca.infrastructure.session.history import derive_turn_history


class _FakeSessionReader:
    """Minimal SessionReader that returns a fixed message list."""

    def __init__(self, messages: list[Message]) -> None:
        self._messages = messages

    def derive_messages(self) -> list[Message]:
        return list(self._messages)

    def snapshot_events(self, from_seq: int = 0, to_seq_exclusive: int | None = None) -> list[Any]:
        return []

    def request_header(self) -> object | None:
        return None


def test_derive_turn_history_none_returns_empty() -> None:
    assert derive_turn_history(None) == []


def test_derive_turn_history_delegates_to_reader() -> None:
    messages: list[Message] = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi", "tool_calls": None},
    ]
    reader = _FakeSessionReader(messages)
    assert derive_turn_history(reader) == messages


def test_derive_turn_history_returns_copy() -> None:
    messages: list[Message] = [{"role": "user", "content": "x"}]
    reader = _FakeSessionReader(messages)
    result = derive_turn_history(reader)
    result.append({"role": "assistant", "content": "y"})
    # The reader's list is not mutated by the caller.
    assert len(messages) == 1


def test_derive_turn_history_message_shape() -> None:
    """The derived history must be OpenAI-compatible dicts with a role key."""
    reader = _FakeSessionReader([{"role": "tool", "content": "result", "tool_call_id": "c1"}])
    history = derive_turn_history(reader)
    assert history[0]["role"] == "tool"
    assert history[0]["tool_call_id"] == "c1"
