"""Tests for RunUiEncoder (ADR-0100 Task 1).

Journal dataclasses → four live SSE event types: reasoning | text | tool | done.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    DecisionMade,
    ReasoningDelta,
    RunScope,
    StampedEvent,
    StepTextDelta,
    TeamRunFinished,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.plugins.transport.run_ui_encoder__encoder_provider import RunUiEncoder


def _events(*items: Any) -> AsyncIterator[Any]:
    async def _gen() -> AsyncIterator[Any]:
        for it in items:
            yield it

    return _gen()


def _parse_frames(raw_frames: list[bytes]) -> list[dict[str, Any]]:
    """Parse SSE frames into {id, event, data} dicts."""
    out: list[dict[str, Any]] = []
    for raw in raw_frames:
        text = raw.decode("utf-8")
        assert not text.startswith("data: [DONE]"), "must not emit [DONE]"
        assert "chat.completion" not in text, "must not emit chat.completion"
        lines = text.strip("\n").split("\n")
        frame: dict[str, Any] = {}
        data_line = ""
        for line in lines:
            if line.startswith("id: "):
                frame["id"] = int(line[len("id: ") :])
            elif line.startswith("event: "):
                frame["event"] = line[len("event: ") :]
            elif line.startswith("data: "):
                data_line = line[len("data: ") :]
        assert "event" in frame and data_line, f"malformed frame: {text!r}"
        frame["data"] = json.loads(data_line)
        out.append(frame)
    return out


async def _encode(*items: Any) -> list[dict[str, Any]]:
    encoder = RunUiEncoder()
    frames = [chunk async for chunk in encoder.encode(_events(*items))]
    return _parse_frames(frames)


@pytest.mark.asyncio
async def test_answer_text_delta() -> None:
    frames = await _encode(StepTextDelta(text_delta="hello", channel="answer", seq=3))
    assert len(frames) == 1
    assert frames[0]["event"] == "text"
    assert frames[0]["data"] == {"text": "hello"}
    assert frames[0]["id"] == 3


@pytest.mark.asyncio
async def test_decision_channel_dropped() -> None:
    frames = await _encode(
        StepTextDelta(text_delta="hidden", channel="decision"),
        AgentRunFinished(status="completed", output_text=""),
    )
    assert all(f["event"] != "text" or f["data"].get("text") != "hidden" for f in frames)
    assert frames[-1]["event"] == "done"
    assert frames[-1]["data"]["status"] == "completed"


@pytest.mark.asyncio
async def test_reasoning_delta() -> None:
    frames = await _encode(ReasoningDelta(text_delta="think", seq=1))
    assert frames == [{"id": 1, "event": "reasoning", "data": {"text": "think"}}]


@pytest.mark.asyncio
async def test_tool_started_done_denied() -> None:
    """ADR-0101 PR-2:ToolStarted 携带 inline ``arguments``(evidence
    不可用退路);ToolInvoked 携带 inline ``arguments``(ToolStarted 同
    ref 不可用时的退路)+ ``output_ref``(ok 时指向 evidence)。"""
    frames = await _encode(
        ToolStarted(
            tool_name="read_file",
            invocation_id="inv-1",
            arguments={"path": "/var/data/x"},
        ),
        ToolInvoked(
            tool_name="read_file",
            invocation_id="inv-1",
            ok=True,
            arguments={"path": "/var/data/x"},
        ),
        ToolDenied(tool_name="write_file", reason="permission denied"),
        AgentRunFinished(status="completed"),
    )
    tool_frames = [f for f in frames if f["event"] == "tool"]
    assert len(tool_frames) == 3
    assert tool_frames[0]["data"]["name"] == "read_file"
    assert tool_frames[0]["data"]["phase"] == "started"
    assert tool_frames[0]["data"]["id"] == "inv-1"
    assert tool_frames[1]["data"]["name"] == "read_file"
    assert tool_frames[1]["data"]["phase"] == "done"
    assert tool_frames[1]["data"]["id"] == "inv-1"
    assert tool_frames[1]["data"]["ok"] is True
    assert tool_frames[2]["data"] == {
        "name": "write_file",
        "phase": "denied",
        "detail": "permission denied",
    }
    assert frames[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_tool_invoked_failure_and_ok_fallback() -> None:
    """ADR-0101 PR-2:ToolInvoked 失败 → output_ref=None, error 字段承载;
    ok → output_ref 可携带 evidence 平面。"""
    frames = await _encode(
        ToolInvoked(tool_name="bash", invocation_id="i", ok=False, error="boom"),
        ToolInvoked(tool_name="noop", invocation_id="i", ok=True),
        AgentRunFinished(status="completed"),
    )
    tool_frames = [f for f in frames if f["event"] == "tool"]
    assert tool_frames[0]["data"]["phase"] == "done"
    assert tool_frames[0]["data"]["detail"] == "boom"
    assert tool_frames[1]["data"]["detail"] == "ok"


@pytest.mark.asyncio
async def test_finished_output_text_fills_empty_stream() -> None:
    frames = await _encode(
        AgentRunFinished(status="completed", output_text="final answer"),
    )
    assert frames[0]["event"] == "text"
    assert frames[0]["data"] == {"text": "final answer"}
    assert frames[1]["event"] == "done"
    assert frames[1]["data"] == {"status": "completed"}


@pytest.mark.asyncio
async def test_answer_deltas_not_duplicated_by_finished() -> None:
    frames = await _encode(
        StepTextDelta(text_delta="hello", channel="answer"),
        AgentRunFinished(status="completed", output_text="hello"),
    )
    text_frames = [f for f in frames if f["event"] == "text"]
    assert len(text_frames) == 1
    assert text_frames[0]["data"]["text"] == "hello"
    assert frames[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_done_status_mapping() -> None:
    frames = await _encode(AgentRunFinished(status="waiting_input", error="need confirm"))
    assert frames[-1]["event"] == "done"
    assert frames[-1]["data"]["status"] == "awaiting_human"
    assert frames[-1]["data"].get("error") == "need confirm"


@pytest.mark.asyncio
async def test_failed_done_includes_error_when_no_text() -> None:
    frames = await _encode(AgentRunFinished(status="failed", error="boom", output_text=""))
    assert len(frames) == 1
    assert frames[0]["event"] == "done"
    assert frames[0]["data"] == {"status": "failed", "error": "boom"}


@pytest.mark.asyncio
async def test_no_done_sentinel_or_chat_completion() -> None:
    encoder = RunUiEncoder()
    raw = [
        chunk
        async for chunk in encoder.encode(
            _events(
                StepTextDelta(text_delta="x", channel="answer"),
                AgentRunFinished(status="completed"),
            )
        )
    ]
    joined = b"".join(raw).decode("utf-8")
    assert "[DONE]" not in joined
    assert "chat.completion" not in joined
    assert "object" not in joined or '"object"' not in joined


@pytest.mark.asyncio
async def test_decision_made_fills_when_stream_empty() -> None:
    frames = await _encode(
        DecisionMade(response_text="from decision"),
        AgentRunFinished(status="completed", output_text="from finished"),
    )
    text_frames = [f for f in frames if f["event"] == "text"]
    assert len(text_frames) == 1
    assert text_frames[0]["data"]["text"] == "from decision"


@pytest.mark.asyncio
async def test_decision_made_fills_after_reasoning_when_answer_empty() -> None:
    frames = await _encode(
        ReasoningDelta(text_delta="r"),
        DecisionMade(response_text="from decision"),
        AgentRunFinished(status="completed", output_text=""),
    )
    text_frames = [f for f in frames if f["event"] == "text"]
    assert [f["data"]["text"] for f in text_frames] == ["from decision"]
    assert frames[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_decision_made_skipped_after_answer_text() -> None:
    frames = await _encode(
        StepTextDelta(text_delta="already", channel="answer"),
        DecisionMade(response_text="should skip"),
        AgentRunFinished(status="completed", output_text=""),
    )
    text_frames = [f for f in frames if f["event"] == "text"]
    assert [f["data"]["text"] for f in text_frames] == ["already"]


@pytest.mark.asyncio
async def test_member_agent_run_finished_does_not_close_stream() -> None:
    member = StampedEvent(
        seq=1,
        ts=1.0,
        scope=RunScope(agent_role="member", parent_run_id="root"),
        event=AgentRunFinished(status="completed", output_text="member answer"),
    )
    more = StampedEvent(
        seq=2,
        ts=2.0,
        scope=RunScope(agent_role="lead"),
        event=StepTextDelta(text_delta="lead text", channel="answer"),
    )
    team = StampedEvent(
        seq=3,
        ts=3.0,
        scope=RunScope(agent_role="team"),
        event=TeamRunFinished(status="completed"),
    )
    frames = await _encode(member, more, team)
    done_frames = [f for f in frames if f["event"] == "done"]
    assert len(done_frames) == 1
    assert frames[-1]["event"] == "done"
    assert frames[-1]["id"] == 3
    assert frames[-1]["data"]["status"] == "completed"
    texts = [f["data"]["text"] for f in frames if f["event"] == "text"]
    assert texts == ["lead text"]


@pytest.mark.asyncio
async def test_error_status_maps_to_failed() -> None:
    frames = await _encode(AgentRunFinished(status="error", error="boom", output_text=""))
    assert frames[-1]["event"] == "done"
    assert frames[-1]["data"] == {"status": "failed", "error": "boom"}


@pytest.mark.asyncio
async def test_stamped_event_uses_outer_seq() -> None:
    stamped = StampedEvent(
        seq=42,
        ts=1.0,
        scope=RunScope(agent_role="solo"),
        event=StepTextDelta(text_delta="hi", channel="answer", seq=7),
    )
    frames = await _encode(stamped)
    assert frames[0]["id"] == 42
    assert frames[0]["event"] == "text"
    assert frames[0]["data"] == {"text": "hi"}


@pytest.mark.asyncio
async def test_empty_deltas_skipped() -> None:
    frames = await _encode(
        ReasoningDelta(text_delta=""),
        StepTextDelta(text_delta="", channel="answer"),
        AgentRunFinished(status="canceled"),
    )
    assert all(f["event"] != "reasoning" for f in frames)
    assert frames[-1]["data"]["status"] == "canceled"
