"""LiveTail → Journal SSE on ``RegistryRunAdapter.stream_run_live``.

Agent observation is ``GET /runs/{id}/live`` (event = class name), not OpenAI
ChatCompletion chunks from ``stream_chat_completion``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from gateway.runs.legacy_adapter import RegistryRunAdapter
from gateway.runs.session import RunRegistry, RunSession
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    ReasoningDelta,
    RunScope,
    StampedEvent,
    StepTextDelta,
    ToolInvoked,
    ToolStarted,
)
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail

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
        jsonl_path=Path("/var/data/lca-nonexistent.jsonl"),
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
    assert "event: ReasoningDelta" in joined
    assert "event: StepTextDelta" in joined
    assert "event: ToolStarted" in joined
    assert "event: AgentRunFinished" in joined
    assert "data: [DONE]" not in joined
    assert "chat.completion" not in joined

    frames = _parse_sse(raw)

    def _payload(frame: dict[str, Any]) -> dict[str, Any]:
        data = frame["data"]
        inner = data.get("data") if isinstance(data, dict) else None
        return inner if isinstance(inner, dict) else data

    assert frames[0]["event"] == "ReasoningDelta"
    assert _payload(frames[0]).get("text_delta") == "Let me think…"
    tool_frames = [frame for frame in frames if frame["event"] in {"ToolStarted", "ToolInvoked"}]
    assert [frame["event"] for frame in tool_frames] == ["ToolStarted", "ToolInvoked"]
    assert any(_payload(frame).get("tool_name") == "read_file" for frame in tool_frames)
    text_frames = [frame for frame in frames if frame["event"] == "StepTextDelta"]
    assert _payload(text_frames[-1]).get("text_delta") == "Hello world"
    assert frames[-1]["event"] == "AgentRunFinished"


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
        jsonl_path=Path("/var/data/lca-nonexistent.jsonl"),
        tail=tail,
        question="q",
        user_text="u",
        mode="solo",
    )
    registry.put(session)
    tail.on_event(_stamped(StepTextDelta(text_delta="only this", channel="answer")))
    tail.close()

    raw = await _drain(adapter.stream_run_live(session.run_id, 0))
    frames = _parse_sse(raw)
    assert [frame["event"] for frame in frames if frame["event"] != "LiveGap"] == ["StepTextDelta"]
    joined = b"".join(raw).decode("utf-8")
    assert "data: [DONE]" not in joined
    assert "chat.completion" not in joined
