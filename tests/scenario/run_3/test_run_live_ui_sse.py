"""GET /runs/{id}/live emits four UI SSE events (ADR-0100)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from lca.contracts.models.observability.journal.journal import (
    AgentRunFinished,
    ReasoningDelta,
    RunScope,
    StampedEvent,
    StepTextDelta,
    TeamRunFinished,
    ToolInvoked,
    ToolStarted,
)
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunRegistry,
    RunSession,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.legacy.adapter import RegistryRunAdapter

_SEQ = [0]


def _stamped(payload: Any, *, parent_run_id: str | None = None) -> StampedEvent:
    _SEQ[0] += 1
    seq = _SEQ[0]
    return StampedEvent(
        seq=seq,
        ts=float(seq),
        scope=RunScope(parent_run_id=parent_run_id),
        event_type=type(payload).__name__,
        data={},
        event=payload,
    )


def _seed_journal(registry: RunRegistry, run_id: str = "run-live-ui") -> RunSession:
    tail = LiveTail()
    session = RunSession(
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        spine_path=Path("/var/data/lca-nonexistent.jsonl"),
        tail=tail,
        question="hello",
        user_text="hello",
        mode="solo",
    )
    registry.put(session)
    tail.on_event(_stamped(ReasoningDelta(text_delta="think-token")))
    tail.on_event(
        _stamped(
            ToolStarted(
                tool_name="read_file",
                invocation_id="call-live",
                arguments={"path": "/var/data/x"},
            )
        )
    )
    tail.on_event(
        _stamped(
            ToolInvoked(
                tool_name="read_file",
                invocation_id="call-live",
                ok=True,
            )
        )
    )
    tail.on_event(_stamped(StepTextDelta(text_delta="answer-token", channel="answer")))
    tail.on_event(_stamped(AgentRunFinished(status="completed")))
    tail.close()
    return session


def _app(registry: RunRegistry) -> Starlette:
    """Minimal Starlette app with only the live SSE route (no OpenAI compat imports)."""
    from lca.plugins.transport.webserver.handlers.runs.api.query_endpoints import stream_run_live

    application = Starlette()
    application.state.run_port = RegistryRunAdapter(registry)
    application.add_route(
        "/runs/{run_id}/live",
        stream_run_live,
        methods=["GET", "OPTIONS"],
    )
    return application


def _parse_sse(body: bytes) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for block in body.decode("utf-8").split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        frame: dict[str, Any] = {}
        data_line = ""
        for line in block.split("\n"):
            if line.startswith("id: "):
                frame["id"] = int(line[len("id: ") :])
            elif line.startswith("event: "):
                frame["event"] = line[len("event: ") :]
            elif line.startswith("data: "):
                data_line = line[len("data: ") :]
        if "event" not in frame or not data_line:
            continue
        frame["data"] = json.loads(data_line)
        frames.append(frame)
    return frames


async def _drain(bytes_iter: Any) -> list[bytes]:
    return [raw async for raw in bytes_iter if raw]


def test_live_route_is_registered() -> None:
    from lca.plugins.transport.webserver.routes_2.routes_runs_sessions import ROUTE_SPECS

    paths = {spec.path for spec in ROUTE_SPECS}
    assert "/runs/{run_id}/live" in paths


def test_get_live_unknown_run_returns_404() -> None:
    client = TestClient(_app(RunRegistry()))
    response = client.get("/runs/missing-run/live")
    assert response.status_code == 404
    assert response.json() == {"error": "run not found"}


def test_get_live_emits_four_ui_events() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    session = _seed_journal(registry)
    client = TestClient(_app(registry))
    response = client.get(f"/runs/{session.run_id}/live")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    body = response.content.decode("utf-8")
    names = [line[len("event: ") :] for line in body.splitlines() if line.startswith("event: ")]
    assert "reasoning" in names
    assert "text" in names
    assert names.count("tool") == 2
    assert "done" in names
    assert "ReasoningDelta" not in names
    assert "AgentRunFinished" not in names

    frames = _parse_sse(response.content)
    assert frames[0]["event"] == "reasoning"
    assert frames[0]["data"] == {"text": "think-token"}
    assert frames[-1]["event"] == "done"
    assert frames[-1]["data"]["status"] == "completed"


def test_get_live_has_no_done_sentinel_or_chat_completion() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    session = _seed_journal(registry, run_id="run-no-openai")
    client = TestClient(_app(registry))
    response = client.get(f"/runs/{session.run_id}/live")
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "data: [DONE]" not in body
    assert "[DONE]" not in body
    assert "chat.completion" not in body
    assert "event: deltas" not in body
    assert "event: projection." not in body
    assert "event: terminal" not in body


def test_get_live_after_skips_earlier_seqs() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    session = _seed_journal(registry, run_id="run-after")
    client = TestClient(_app(registry))
    response = client.get(f"/runs/{session.run_id}/live", params={"after": 1})
    assert response.status_code == 200
    frames = _parse_sse(response.content)
    assert all(frame["id"] > 1 for frame in frames)
    assert all(frame["event"] != "reasoning" for frame in frames)
    assert "tool" in [frame["event"] for frame in frames]
    assert frames[-1]["event"] == "done"


def test_get_live_ignores_last_event_id_header() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    session = _seed_journal(registry, run_id="run-leid")
    client = TestClient(_app(registry))
    response = client.get(
        f"/runs/{session.run_id}/live",
        headers={"Last-Event-ID": "99"},
    )
    assert response.status_code == 200
    frames = _parse_sse(response.content)
    assert frames[0]["id"] == 1
    assert frames[0]["event"] == "reasoning"


@pytest.mark.asyncio
async def test_stream_run_live_emits_ui_frames_from_livetail() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)
    session = _seed_journal(registry, run_id="run-adapter")
    raw = await _drain(adapter.stream_run_live(session.run_id, 0))
    joined = b"".join(raw).decode("utf-8")
    assert "event: reasoning" in joined
    assert "event: text" in joined
    assert "event: tool" in joined
    assert "event: done" in joined
    assert "event: ReasoningDelta" not in joined
    frames = _parse_sse(b"".join(raw))
    assert frames[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_stream_run_live_after_skips_earlier_seqs() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)
    session = _seed_journal(registry, run_id="run-adapter-after")
    raw = await _drain(adapter.stream_run_live(session.run_id, 3))
    frames = _parse_sse(b"".join(raw))
    assert all(frame["id"] > 3 for frame in frames)
    assert [frame["event"] for frame in frames] == ["text", "done"]


@pytest.mark.asyncio
async def test_stream_run_live_emits_failed_done_when_tail_closes_without_finish() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)
    tail = LiveTail()
    session = RunSession(
        run_id="run-unfinished",
        trace_id="trace-unfinished",
        spine_path=Path("/var/data/lca-nonexistent.jsonl"),
        tail=tail,
        question="q",
        user_text="u",
        mode="solo",
        error="ImportError: boom",
    )
    registry.put(session)
    tail.on_event(_stamped(StepTextDelta(text_delta="partial", channel="answer")))
    tail.close()

    raw = await _drain(adapter.stream_run_live(session.run_id, 0))
    frames = _parse_sse(b"".join(raw))
    assert [frame["event"] for frame in frames] == ["text", "done"]
    assert frames[-1]["data"] == {"status": "failed", "error": "ImportError: boom"}


@pytest.mark.asyncio
async def test_stream_run_live_no_done_when_tail_closes_while_running() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)
    tail = LiveTail()
    session = RunSession(
        run_id="run-still-running",
        trace_id="trace-still-running",
        spine_path=Path("/var/data/lca-nonexistent.jsonl"),
        tail=tail,
        question="q",
        user_text="u",
        mode="solo",
    )
    from lca.contracts.observability.registry.status import RunLifecycleStatus

    session.status = RunLifecycleStatus.RUNNING
    registry.put(session)
    tail.on_event(_stamped(StepTextDelta(text_delta="partial", channel="answer")))
    tail.close()

    raw = await _drain(adapter.stream_run_live(session.run_id, 0))
    frames = _parse_sse(b"".join(raw))
    assert [frame["event"] for frame in frames] == ["text"]
    assert all(frame["event"] != "done" for frame in frames)


@pytest.mark.asyncio
async def test_stream_run_live_emits_completed_done_from_session_status() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)
    tail = LiveTail()
    session = RunSession(
        run_id="run-completed-no-journal-finish",
        trace_id="trace-completed-no-journal-finish",
        spine_path=Path("/var/data/lca-nonexistent.jsonl"),
        tail=tail,
        question="q",
        user_text="u",
        mode="solo",
    )
    from lca.contracts.observability.registry.status import RunLifecycleStatus

    session.status = RunLifecycleStatus.COMPLETED
    registry.put(session)
    tail.on_event(_stamped(StepTextDelta(text_delta="answer", channel="answer")))
    tail.close()

    raw = await _drain(adapter.stream_run_live(session.run_id, 0))
    frames = _parse_sse(b"".join(raw))
    assert [frame["event"] for frame in frames] == ["text", "done"]
    assert frames[-1]["data"] == {"status": "completed"}


@pytest.mark.asyncio
async def test_stream_run_live_emits_nested_agent_run_finished() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)
    tail = LiveTail()
    session = RunSession(
        run_id="run-team-live",
        trace_id="trace-team-live",
        spine_path=Path("/var/data/lca-nonexistent.jsonl"),
        tail=tail,
        question="q",
        user_text="u",
        mode="team",
    )
    registry.put(session)
    tail.on_event(
        _stamped(AgentRunFinished(status="completed", output_text="member"), parent_run_id="root")
    )
    tail.on_event(_stamped(StepTextDelta(text_delta="after-member", channel="answer")))
    tail.on_event(_stamped(TeamRunFinished(status="completed")))
    tail.close()

    raw = await _drain(adapter.stream_run_live(session.run_id, 0))
    frames = _parse_sse(b"".join(raw))
    names = [frame["event"] for frame in frames]
    assert names == ["text", "done"]
    assert frames[-1]["data"]["status"] == "completed"
