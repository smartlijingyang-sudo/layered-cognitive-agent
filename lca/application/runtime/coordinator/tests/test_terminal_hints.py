"""resolve_live_terminal_hint maps RunSession status to the canonical
6-value status enum the AgentGateway expects.

Mirrors the native `STREAM_END_STATUSES` set in
`apps/server/src/modules/AgentRuntime/AgentRuntimeCoordinator.ts:30-34` —
`done | error | interrupted | waiting_for_human` are stream-terminal.
`running | waiting_for_async_tool` are not.
"""

from unittest.mock import MagicMock

import pytest

from lca.application.runtime.coordinator.terminal_hints import (
    is_stream_terminal_status,
    resolve_live_terminal_hint,
)


@pytest.mark.parametrize(
    "status,expected",
    [
        ("done", "completed"),
        ("completed", "completed"),
        ("error", "error"),
        ("interrupted", "interrupted"),
        ("waiting_input", "waiting_input"),
        ("waiting_for_human", "waiting_input"),
        ("awaiting_human", "waiting_input"),
        ("input-required", "waiting_input"),
        ("running", "running"),
        ("paused", "running"),
    ],
)
def test_resolve_live_terminal_hint_maps_status(status: str, expected: str) -> None:
    session = MagicMock()
    session.status = status
    session.error = None
    assert resolve_live_terminal_hint(session) == expected


def test_resolve_live_terminal_hint_with_error_falls_back_to_error() -> None:
    session = MagicMock()
    session.status = "done"
    session.error = "something broke"
    assert resolve_live_terminal_hint(session) == "error"


@pytest.mark.parametrize(
    "status", ["done", "error", "interrupted", "waiting_for_human", "completed", "waiting_input"]
)
def test_is_stream_terminal_status_true_for_terminal(status: str) -> None:
    assert is_stream_terminal_status(status) is True


@pytest.mark.parametrize("status", ["running", "waiting_for_async_tool", "paused"])
def test_is_stream_terminal_status_false_for_live(status: str) -> None:
    assert is_stream_terminal_status(status) is False
