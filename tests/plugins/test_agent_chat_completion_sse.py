"""LiveTail → four UI SSE events on ``RegistryRunAdapter.stream_run_live``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.models.observability.journal.journal import (
    AgentRunFinished,
    ReasoningDelta,
    RunScope,
    StampedEvent,
    StepTextDelta,
    ToolInvoked,
    ToolStarted,
)
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunRegistry,
    RunSession,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.legacy.adapter import RegistryRunAdapter

_seq_counter = [0]


def _stamped(payload: Any) -> StampedEvent:
    """Wrap an event payload with the minimum metadata the LiveTail requires."""
    _seq_counter[0] += 1
    seq = _seq_counter[0]
    return StampedEvent(
        seq=seq,
        ts=seq,
        scope=RunScope(trace_id="t", run_id="r"),
        event_type=type(payload).__name__,
        data={},
        event=payload,
    )


async def _drain(bytes_iter: Any) -> list[bytes]:
    return [raw async for raw in bytes_iter if raw]


def _parse_sse(raw_frames: list[bytes]) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for block in b"".join(raw_frames).decode("utf-8").split("\n\n"):
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


@pytest.mark.asyncio
async def test_stream_run_live_emits_ui_wire_with_reasoning_tool_and_finish() -> None:
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)

    tail = LiveTail()
    session = RunSession(
        run_id="run-test-1",
        trace_id="trace-test-1",
        spine_path=Path("/var/data/lca-nonexistent.jsonl"),
        tail=tail,
        question="q",
        user_text="u",
        mode="solo",
    )
    registry.put(session)

    tail.on_event(_stamped(ReasoningDelta(text_delta="Let me think…")))
    tail.on_event(
        _stamped(
            ToolStarted(
                tool_name="read_file",
                invocation_id="call-1",
                arguments={"path": "/var/data/x"},
            )
        )
    )
    tail.on_event(
        _stamped(
            ToolInvoked(
                tool_name="read_file",
                invocation_id="call-1",
                ok=True,
            )
        )
    )
    tail.on_event(_stamped(StepTextDelta(text_delta="Hello world", channel="answer")))
    tail.on_event(_stamped(AgentRunFinished()))
    tail.close()

    raw = await _drain(adapter.stream_run_live(session.run_id, 0))
    joined = b"".join(raw).decode("utf-8")
    assert "event: reasoning" in joined
    assert "event: text" in joined
    assert "event: tool" in joined
    assert "event: done" in joined
    assert "event: ReasoningDelta" not in joined

    frames = _parse_sse(raw)
    assert frames[0]["event"] == "reasoning"
    assert frames[0]["data"]["text"] == "Let me think…"
    tool_frames = [frame for frame in frames if frame["event"] == "tool"]
    assert len(tool_frames) == 2
    text_frames = [frame for frame in frames if frame["event"] == "text"]
    assert text_frames[-1]["data"]["text"] == "Hello world"
    assert frames[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_stream_run_live_returns_empty_for_unknown_run() -> None:
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)
    out = []
    async for line in adapter.stream_run_live("nonexistent-run", 0):
        out.append(line)
    assert out == []


@pytest.mark.asyncio
async def test_stream_run_live_emits_failed_done_when_no_finish() -> None:
    """Source stream drained without ``AgentRunFinished`` must still close."""
    _seq_counter[0] = 0
    registry = RunRegistry()
    adapter = RegistryRunAdapter(registry)

    tail = LiveTail()
    session = RunSession(
        run_id="run-test-2",
        trace_id="trace-test-2",
        spine_path=Path("/var/data/lca-nonexistent.jsonl"),
        tail=tail,
        question="q",
        user_text="u",
        mode="solo",
        error="think phase exploded",
    )
    registry.put(session)
    tail.on_event(_stamped(StepTextDelta(text_delta="only this", channel="answer")))
    tail.close()

    raw = await _drain(adapter.stream_run_live(session.run_id, 0))
    frames = _parse_sse(raw)
    assert [frame["event"] for frame in frames] == ["text", "done"]
    assert frames[-1]["data"] == {"status": "failed", "error": "think phase exploded"}
