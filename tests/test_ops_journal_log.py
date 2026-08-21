"""Process journal + ops SSE adapter — lca-ops logs is journal, not a file."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from gateway.app import create_app
from gateway.runs.execute import create_run_session
from gateway.runs.process_journal import ProcessJournal
from gateway.runs.session import RunRegistry
from lca.layer0_infra.observability.run_locator_fs import FilesystemRunLocator
from lca.contracts.models.observability.journal import (
    AgentRunStarted,
    DecisionMade,
    ReasoningDelta,
    RunScope,
    StampedEvent,
    ToolStarted,
)
from lca.layer0_infra.observability import bind_backends, record
from lca.layer0_infra.ops.journal_log import (
    extract_seq_from_record,
    parse_sse_block,
    sse_record_to_stamped,
)


def test_parse_sse_skips_keepalive() -> None:
    assert parse_sse_block(": keepalive") is None


def test_adapter_converts_decision_to_stamped() -> None:
    record = {
        "schema": "journal.v1",
        "seq": 42,
        "ts": 1_700_000_000.0,
        "scope": {"run_id": "run_abcdefghijkl", "agent_role": "助手", "trace_id": ""},
        "event_type": "DecisionMade",
        "event": {
            "action_type": "use_tool",
            "tool_name": "local_runCommand",
            "rationale_preview": "run it",
        },
    }
    stamped = sse_record_to_stamped(record)
    assert stamped is not None
    assert isinstance(stamped, StampedEvent)
    assert stamped.seq == 42
    assert isinstance(stamped.event, DecisionMade)
    assert stamped.event.action_type == "use_tool"
    assert stamped.event.tool_name == "local_runCommand"


def test_adapter_converts_tool_started() -> None:
    record = {
        "schema": "journal.v1",
        "seq": 1,
        "ts": 1_700_000_000.0,
        "scope": {"run_id": "run_abcdefghijkl", "agent_role": "助手", "trace_id": ""},
        "event_type": "ToolStarted",
        "event": {
            "tool_name": "local_runCommand",
            "arguments_preview": '{"command": "ls"}',
        },
    }
    stamped = sse_record_to_stamped(record)
    assert stamped is not None
    assert isinstance(stamped.event, ToolStarted)
    assert stamped.event.tool_name == "local_runCommand"


def test_adapter_skips_livegap() -> None:
    record = {
        "event_type": "LiveGap",
        "_sse_event": "LiveGap",
        "event": {"oldest_seq": 10},
    }
    assert sse_record_to_stamped(record) is None


def test_adapter_skips_unknown_event() -> None:
    record = {
        "schema": "journal.v1",
        "seq": 1,
        "ts": 1.0,
        "scope": {},
        "event_type": "UnknownFutureEvent",
        "event": {},
    }
    assert sse_record_to_stamped(record) is None


def test_extract_seq() -> None:
    assert extract_seq_from_record({"seq": 42}) == 42
    assert extract_seq_from_record({}) == 0
    assert extract_seq_from_record({"seq": "not_int"}) == 0


def test_process_journal_survives_bind_close() -> None:
    hub = ProcessJournal()
    projector = hub.bind()
    stamped = StampedEvent(
        seq=1,
        ts=1.0,
        scope=RunScope(run_id="r1", agent_role="助手"),
        event=ToolStarted(tool_name="ls", invocation_id="i1"),
    )
    projector.on_event(stamped)
    projector.close()
    assert not hub.tail.is_closed
    assert hub.tail.buffer_size == 1
    assert hub.tail.last_seq == 1


@pytest.mark.asyncio
async def test_create_run_session_publishes_to_process_journal(tmp_path: Path) -> None:
    from lca.harness.profile.lifespan import profile_lifespan

    registry = RunRegistry(locator=FilesystemRunLocator(root=tmp_path))
    async with profile_lifespan("profiles/web-standard.yaml") as state:
        ctx = state["ctx"]
        session = create_run_session(registry, question="q", user_text="q", ctx=ctx)
    assert session.hub is not None
    with bind_backends(session.hub):
        record(AgentRunStarted(agent_role="助手", objective="q"))
        record(DecisionMade(action_type="use_tool", tool_name="ls"))
        record(ReasoningDelta(step=1, text_delta="noise", seq=1))
    assert registry.journal.tail.buffer_size >= 2
    session.hub.close()
    assert not registry.journal.tail.is_closed


@pytest.mark.asyncio
async def test_journal_live_keeps_tool_preview(tmp_path: Path) -> None:
    from lca.harness.profile.lifespan import profile_lifespan

    registry = RunRegistry(locator=FilesystemRunLocator(root=tmp_path))
    async with profile_lifespan("profiles/web-standard.yaml") as state:
        ctx = state["ctx"]
        session = create_run_session(registry, question="q", user_text="q", ctx=ctx)
    assert session.hub is not None
    with bind_backends(session.hub):
        record(
            ToolStarted(
                tool_name="local_runCommand",
                invocation_id="i1",
                arguments_preview='{"command": "ls"}',
            )
        )
    app = create_app(registry)
    with TestClient(app).stream("GET", "/journal/live") as resp:
        assert resp.status_code == 200
        buf = ""
        for chunk in resp.iter_text():
            buf += chunk
            if "\n\n" in buf:
                break
    assert "local_runCommand" in buf
    assert "ls" in buf
    session.hub.close()
