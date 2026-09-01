"""GET /runs/{id}/live emits Journal SSE frames via stamped_to_sse_frame."""

from __future__ import annotations

import json

import pytest

from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    ReasoningDelta,
    RunScope,
    StampedEvent,
    StepTextDelta,
    ToolInvoked,
    ToolStarted,
)
from lca.infrastructure.observability.journal.engine.journal_io import stamped_to_record
from lca.infrastructure.observability.journal.sse.frames import stamped_to_sse_frame
from lca.infrastructure.observability.journal.stream.live_tail import (
    LiveGap,
    LiveTail,
    encode_live_gap,
    iter_live_sse,
)


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
    assert payload["descriptor"]["type"] == record["descriptor"]["type"]
    assert payload["data"] == record["data"]
    assert payload["run_seq"] == 1


@pytest.mark.asyncio
async def test_tool_started_typed_fields_propagate_to_live_sse() -> None:
    """ADR-0101 PR-2:tool 事件 dataclass 不再有 typed 6-key / plugin_state
    字段(0065 §四);SSE 帧 data 仅含事实字段。完整数据经
    ``arguments_ref`` 走 evidence 平面。"""
    tail = LiveTail()
    tail.on_event(
        _stamped(
            1,
            ToolStarted(
                tool_name="execute_code",
                invocation_id="i",
            ),
        )
    )
    tail.close()
    frames = [frame async for frame in iter_live_sse(tail, after_seq=0, heartbeat_s=30)]
    _, _, payload = _parse_frame(frames[0])
    assert payload["data"]["tool_name"] == "execute_code"
    assert payload["data"]["invocation_id"] == "i"
    # typed 6-key 不在 SSE
    for forbidden in ("code", "language", "execution_env", "plugin_state"):
        assert forbidden not in payload["data"]
    # V7:arguments / arguments_ref 至少一个
    assert "arguments" in payload["data"] or "arguments_ref" in payload["data"]


@pytest.mark.asyncio
async def test_ops_stream_keeps_typed_fields_no_preview() -> None:
    """ADR-0101 PR-2:preview 不在 SSE payload;typed 6-key / output_text /
    state_ref / plugin_state 同样不在。SSE 帧只携带事实字段。"""
    tail = LiveTail()
    tail.on_event(
        _stamped(
            1,
            ToolInvoked(
                tool_name="executeCode",
                invocation_id="i",
                ok=True,
                latency_ms=100,
            ),
        )
    )
    tail.close()
    frames = [frame async for frame in iter_live_sse(tail, after_seq=0, heartbeat_s=30)]
    _, _, payload = _parse_frame(frames[0])
    for forbidden in (
        "arguments_preview",
        "result_preview",
        "code",
        "language",
        "command",
        "plugin_state",
        "state_ref",
    ):
        assert forbidden not in payload["data"], f"{forbidden} present in payload"
    # V7:arguments / arguments_ref 至少一个
    assert "arguments" in payload["data"] or "arguments_ref" in payload["data"]


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


@pytest.mark.asyncio
async def test_default_text_channel_filters_decision_deltas() -> None:
    """LobeHub live 默认仅推 answer 通道的 StepTextDelta（ADR-0051 § 九）。"""
    tail = LiveTail()
    tail.on_event(
        _stamped(
            1,
            StepTextDelta(
                step=2,
                text_delta="raw token",
                seq=0,
                channel=StreamChannel.DECISION.value,
            ),
        )
    )
    tail.on_event(
        _stamped(
            2,
            StepTextDelta(
                step=2,
                text_delta="visible",
                seq=1,
                channel=StreamChannel.ANSWER.value,
            ),
        )
    )
    tail.close()
    frames = [frame async for frame in iter_live_sse(tail, after_seq=0, heartbeat_s=30)]
    names = [_parse_frame(frame)[1] for frame in frames]
    assert names == ["StepTextDelta"]
    _, _, payload = _parse_frame(frames[0])
    assert payload["data"]["channel"] == StreamChannel.ANSWER.value


@pytest.mark.asyncio
async def test_text_channel_all_keeps_both_deltas() -> None:
    """ops /journal/live 显式传 ``all`` 时全推（决策通道用于 replay/audit）。"""
    tail = LiveTail()
    tail.on_event(
        _stamped(
            1,
            StepTextDelta(
                step=2,
                text_delta="raw",
                seq=0,
                channel=StreamChannel.DECISION.value,
            ),
        )
    )
    tail.on_event(
        _stamped(
            2,
            StepTextDelta(
                step=2,
                text_delta="vis",
                seq=1,
                channel=StreamChannel.ANSWER.value,
            ),
        )
    )
    tail.close()
    frames = [
        frame
        async for frame in iter_live_sse(
            tail,
            after_seq=0,
            heartbeat_s=30,
            text_channel="all",
        )
    ]
    names = [_parse_frame(frame)[1] for frame in frames]
    assert names == ["StepTextDelta", "StepTextDelta"]


@pytest.mark.asyncio
async def test_text_channel_none_disables_filter() -> None:
    """``text_channel=None`` 不过滤（向后兼容 / 排查用）。"""
    tail = LiveTail()
    tail.on_event(
        _stamped(
            1,
            StepTextDelta(
                step=2,
                text_delta="raw",
                seq=0,
                channel=StreamChannel.DECISION.value,
            ),
        )
    )
    tail.on_event(
        _stamped(
            2,
            StepTextDelta(
                step=2,
                text_delta="vis",
                seq=1,
                channel=StreamChannel.ANSWER.value,
            ),
        )
    )
    tail.close()
    frames = [
        frame
        async for frame in iter_live_sse(
            tail,
            after_seq=0,
            heartbeat_s=30,
            text_channel=None,
        )
    ]
    names = [_parse_frame(frame)[1] for frame in frames]
    assert names == ["StepTextDelta", "StepTextDelta"]


@pytest.mark.asyncio
async def test_gateway_api_iter_live_sse_emits_frames() -> None:
    """ADR-0163 决策 5:the runs/api carrier SSE helper is now a sibling re-export
    stub. The live SSE generator lives at
    :func:`lca.plugins.transport.webserver.handlers.runs.terminal.live_compat.iter_live_sse`
    (a forwarder over :mod:`lca.infrastructure.observability.journal.stream.live_tail`).
    This regression confirms the carrier-facing surface still yields frames
    without the legacy ``redact=`` parameter drift.
    """
    from lca.plugins.transport.webserver.handlers.runs.terminal.live_compat import (
        iter_live_sse as carrier_iter_live_sse,
    )

    tail = LiveTail()
    stamped = _stamped(1, ReasoningDelta(step=0, text_delta="hello", seq=0))
    tail.on_event(stamped)
    tail.close()

    frames = [frame async for frame in carrier_iter_live_sse(tail, after_seq=0, heartbeat_s=30)]
    assert frames, "carrier iter_live_sse yielded no frames"
    frame_id, event_name, payload = _parse_frame(frames[0])
    _ = frame_id
    assert event_name == "ReasoningDelta"
    assert payload["run_seq"] == 1
