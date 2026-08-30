"""GET /runs/{id}/live emits Journal SSE frames (event = class name)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from gateway.routes import build_routes
from gateway.runs.terminal.legacy_adapter import RegistryRunAdapter
from gateway.runs.session.session import RunRegistry, RunSession
from lca.contracts.models.observability.journal import (
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
        jsonl_path=Path("/var/data/lca-nonexistent.jsonl"),
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
    application = Starlette(routes=build_routes())
    application.state.run_port = RegistryRunAdapter(registry)
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
    paths = {route.path for route in build_routes() if hasattr(route, "path")}
    assert "/runs/{run_id}/live" in paths


def test_get_live_unknown_run_returns_404() -> None:
    client = TestClient(_app(RunRegistry()))
    response = client.get("/runs/missing-run/live")
    assert response.status_code == 404
    assert response.json() == {"error": "run not found"}


def _payload(frame: dict[str, Any]) -> dict[str, Any]:
    data = frame["data"]
    inner = data.get("data") if isinstance(data, dict) else None
    return inner if isinstance(inner, dict) else data


def test_get_live_emits_journal_events() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    session = _seed_journal(registry)
    client = TestClient(_app(registry))
    response = client.get(f"/runs/{session.run_id}/live")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert response.headers.get("Cache-Control") == "no-cache"
    assert response.headers.get("Connection") == "keep-alive"
    assert response.headers.get("X-Accel-Buffering") == "no"

    body = response.content.decode("utf-8")
    names = [line[len("event: ") :] for line in body.splitlines() if line.startswith("event: ")]
    assert "ReasoningDelta" in names
    assert "StepTextDelta" in names
    assert "ToolStarted" in names
    assert "ToolInvoked" in names
    assert "AgentRunFinished" in names
    assert "deltas" not in names
    assert "terminal" not in names

    frames = _parse_sse(response.content)
    assert frames[0]["event"] == "ReasoningDelta"
    assert _payload(frames[0]).get("text_delta") == "think-token"
    assert frames[0]["id"] == 1
    assert [
        frame["event"] for frame in frames if frame["event"] in {"ToolStarted", "ToolInvoked"}
    ] == [
        "ToolStarted",
        "ToolInvoked",
    ]
    text_frames = [frame for frame in frames if frame["event"] == "StepTextDelta"]
    assert _payload(text_frames[-1]).get("text_delta") == "answer-token"
    assert frames[-1]["event"] == "AgentRunFinished"


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
    assert all(frame["event"] != "ReasoningDelta" for frame in frames)
    names = [frame["event"] for frame in frames]
    assert "ToolStarted" in names
    assert "StepTextDelta" in names
    assert "AgentRunFinished" in names


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
    assert frames[0]["event"] == "ReasoningDelta"


@pytest.mark.asyncio
async def test_stream_run_live_emits_ui_frames_from_livetail() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)
    session = _seed_journal(registry, run_id="run-adapter")
    raw = await _drain(adapter.stream_run_live(session.run_id, 0))
    joined = b"".join(raw).decode("utf-8")
    assert "event: ReasoningDelta" in joined
    assert "event: StepTextDelta" in joined
    assert "event: ToolStarted" in joined
    assert "event: AgentRunFinished" in joined
    assert "data: [DONE]" not in joined
    assert "chat.completion" not in joined
    frames = _parse_sse(b"".join(raw))
    assert frames[0]["id"] == 1
    assert frames[-1]["event"] == "AgentRunFinished"


@pytest.mark.asyncio
async def test_stream_run_live_after_skips_earlier_seqs() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)
    session = _seed_journal(registry, run_id="run-adapter-after")
    raw = await _drain(adapter.stream_run_live(session.run_id, 3))
    frames = _parse_sse(b"".join(raw))
    assert all(frame["id"] > 3 for frame in frames)
    assert [frame["event"] for frame in frames] == ["StepTextDelta", "AgentRunFinished"]


@pytest.mark.asyncio
async def test_stream_run_live_emits_failed_done_when_tail_closes_without_finish() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)
    tail = LiveTail()
    session = RunSession(
        run_id="run-unfinished",
        trace_id="trace-unfinished",
        jsonl_path=Path("/var/data/lca-nonexistent.jsonl"),
        tail=tail,
        question="q",
        user_text="u",
        mode="solo",
    )
    registry.put(session)
    tail.on_event(_stamped(StepTextDelta(text_delta="partial", channel="answer")))
    tail.close()

    raw = await _drain(adapter.stream_run_live(session.run_id, 0))
    frames = _parse_sse(b"".join(raw))
    assert [frame["event"] for frame in frames] == ["StepTextDelta"]
    assert _payload(frames[-1]).get("text_delta") == "partial"


@pytest.mark.asyncio
async def test_stream_run_live_emits_nested_agent_run_finished() -> None:
    _SEQ[0] = 0
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)
    tail = LiveTail()
    session = RunSession(
        run_id="run-team-live",
        trace_id="trace-team-live",
        jsonl_path=Path("/var/data/lca-nonexistent.jsonl"),
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
    assert names == ["AgentRunFinished", "StepTextDelta", "TeamRunFinished"]
    texts = [
        _payload(frame).get("text_delta") for frame in frames if frame["event"] == "StepTextDelta"
    ]
    assert texts == ["after-member"]
