"""GET /runs/{id}/live emits Journal SSE frames via stamped_to_sse_frame."""

from __future__ import annotations

import json

import pytest

from gateway.runs.api import encode_live_gap, iter_live_sse
from gateway.runs.live import LiveGap, LiveTail
from lca.contracts.models.observability.journal import (
    ReasoningDelta,
    RunScope,
    StampedEvent,
    ToolInvoked,
    ToolStarted,
)
from lca.layer0_infra.observability.journal.journal_io import stamped_to_record
from lca.layer0_infra.observability.journal.sse_frames import stamped_to_sse_frame


def _stamped(seq: int, event: object) -> StampedEvent:
    return StampedEvent(
        seq=seq,
        ts=float(seq),
        scope=RunScope(trace_id="t", run_id="r"),
        event=event,
    )


def _parse_frame(raw: bytes) -> tuple[str, str, dict]:
    text = raw.decode()
    event_name = ""
    data_line = ""
    frame_id = ""
    for line in text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:]
        elif line.startswith("data: "):
            data_line = line[6:]
        elif line.startswith("id: "):
            frame_id = line[4:]
    payload = json.loads(data_line) if data_line else {}
    return frame_id, event_name, payload


@pytest.mark.asyncio
async def test_live_event_names_are_journal_class_names() -> None:
    tail = LiveTail()
    thinking = _stamped(1, ReasoningDelta(step=0, text_delta="think", seq=0))
    tool = _stamped(
        2,
        ToolStarted(
            tool_name="execute_code",
            invocation_id="inv1",
            plugin_state={"code": "print(1)", "language": "python"},
        ),
    )
    tail.on_event(thinking)
    tail.on_event(tool)
    tail.close()
    frames = [frame async for frame in iter_live_sse(tail, after_seq=0, heartbeat_s=30)]
    names = [_parse_frame(frame)[1] for frame in frames]
    assert names == ["ReasoningDelta", "ToolStarted"]
    assert "thinking.delta" not in names


@pytest.mark.asyncio
async def test_live_data_matches_stamped_to_record() -> None:
    tail = LiveTail()
    stamped = _stamped(1, ReasoningDelta(step=0, text_delta="hi", seq=0))
    tail.on_event(stamped)
    tail.close()
    frames = [frame async for frame in iter_live_sse(tail, after_seq=0, heartbeat_s=30)]
    _, event_name, payload = _parse_frame(frames[0])
    record = stamped_to_record(stamped)
    assert event_name == "ReasoningDelta"
    assert payload["event_type"] == record["event_type"]
    assert payload["event"] == record["event"]
    assert payload["seq"] == 1


@pytest.mark.asyncio
async def test_tool_started_plugin_state_is_not_rewritten() -> None:
    state = {"code": "print(1)", "language": "python", "executionEnv": "sandbox"}
    tail = LiveTail()
    tail.on_event(
        _stamped(1, ToolStarted(tool_name="execute_code", invocation_id="i", plugin_state=state))
    )
    tail.close()
    frames = [frame async for frame in iter_live_sse(tail, after_seq=0, heartbeat_s=30)]
    _, _, payload = _parse_frame(frames[0])
    assert payload["event"]["plugin_state"] == state


@pytest.mark.asyncio
async def test_ops_stream_keeps_preview_strings() -> None:
    tail = LiveTail()
    tail.on_event(
        _stamped(
            1,
            ToolInvoked(
                tool_name="ls",
                arguments_preview="ls -la",
                result_preview="ok",
                invocation_id="i",
            ),
        )
    )
    tail.close()
    frames = [
        frame async for frame in iter_live_sse(tail, after_seq=0, heartbeat_s=30, redact=False)
    ]
    _, _, payload = _parse_frame(frames[0])
    assert payload["event"]["arguments_preview"] == "ls -la"
    assert payload["event"]["result_preview"] == "ok"


@pytest.mark.asyncio
async def test_compose_emits_keepalive_on_timeout() -> None:
    tail = LiveTail()
    agen = iter_live_sse(tail, after_seq=0, heartbeat_s=0.01)
    frame = await agen.__anext__()
    assert frame == b": keepalive\n\n"
    tail.close()
    leftover = [item async for item in agen]
    assert leftover == []


@pytest.mark.asyncio
async def test_last_event_id_skips_seen_seq() -> None:
    tail = LiveTail()
    tail.on_event(_stamped(1, ReasoningDelta(step=0, text_delta="a", seq=0)))
    tail.on_event(_stamped(2, ReasoningDelta(step=0, text_delta="b", seq=0)))
    tail.close()
    frames = [frame async for frame in iter_live_sse(tail, after_seq=1, heartbeat_s=30)]
    ids = [_parse_frame(frame)[0] for frame in frames]
    assert ids == ["2"]


def test_live_gap_frame_has_no_id() -> None:
    raw = encode_live_gap(LiveGap(requested_seq=0, oldest_seq=12))
    text = raw.decode()
    assert "event: LiveGap" in text
    assert "id:" not in text
    payload = json.loads(text.split("data: ", 1)[1].strip())
    assert payload == {"requested_seq": 0, "oldest_seq": 12}


def test_live_uses_stamped_to_sse_frame() -> None:
    stamped = _stamped(9, ReasoningDelta(step=0, text_delta="z", seq=0))
    assert stamped_to_sse_frame(stamped).startswith("id: 9\nevent: ReasoningDelta\n")
