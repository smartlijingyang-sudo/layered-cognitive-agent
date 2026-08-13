"""LiveTail is a JournalProjector: subscribe, replay, gap, close, overflow."""

from __future__ import annotations

import asyncio
import logging

import pytest
import structlog

from gateway.runs.live import LiveGap, LiveTail
from lca.contracts.models.observability.journal import ReasoningDelta, RunScope, StampedEvent
from lca.contracts.protocols import JournalProjector


def _stamped(seq: int, text: str = "x") -> StampedEvent:
    return StampedEvent(
        seq=seq,
        ts=float(seq),
        scope=RunScope(trace_id="t", run_id="r"),
        event=ReasoningDelta(step=0, text_delta=text, seq=seq),
    )


def test_live_tail_is_journal_projector() -> None:
    tail = LiveTail()
    assert isinstance(tail, JournalProjector)
    assert callable(tail.on_event)
    assert callable(tail.flush)
    assert callable(tail.close)


@pytest.mark.asyncio
async def test_on_event_then_subscribe_replays_same_stamped_object() -> None:
    tail = LiveTail()
    event = _stamped(1, "hello")
    tail.on_event(event)
    tail.close()
    items = [item async for item in tail.subscribe(after_seq=0)]
    assert items == [event]
    assert items[0] is event


@pytest.mark.asyncio
async def test_subscribe_then_on_event_does_not_drop() -> None:
    tail = LiveTail()
    received: list[StampedEvent | LiveGap] = []

    async def consume() -> None:
        async for item in tail.subscribe(after_seq=0):
            received.append(item)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    live = _stamped(1, "live")
    tail.on_event(live)
    tail.close()
    await task
    assert received == [live]
    assert received[0] is live


@pytest.mark.asyncio
async def test_subscribe_after_seq_skips_seen() -> None:
    tail = LiveTail()
    first = _stamped(1)
    second = _stamped(2)
    tail.on_event(first)
    tail.on_event(second)
    tail.close()
    items = [item async for item in tail.subscribe(after_seq=1)]
    assert items == [second]


@pytest.mark.asyncio
async def test_subscribe_emits_live_gap_when_buffer_evicted() -> None:
    tail = LiveTail()
    for seq in range(1, tail.buffer_capacity + 2):
        tail.on_event(_stamped(seq))
    tail.close()
    items = [item async for item in tail.subscribe(after_seq=0)]
    assert isinstance(items[0], LiveGap)
    assert items[0].requested_seq == 0
    assert items[0].oldest_seq == 2
    assert all(not isinstance(item, LiveGap) or item is items[0] for item in items)
    assert items[1].seq == 2  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_close_ends_subscription_and_is_idempotent() -> None:
    tail = LiveTail()
    tail.on_event(_stamped(1))
    tail.close()
    first = [item async for item in tail.subscribe(after_seq=0)]
    assert len(first) == 1
    tail.close()
    second = [item async for item in tail.subscribe(after_seq=0)]
    assert [item.seq for item in second if isinstance(item, StampedEvent)] == [1]


@pytest.mark.asyncio
async def test_consecutive_queue_full_evicts_subscriber(caplog: pytest.LogCaptureFixture) -> None:
    tail = LiveTail()
    received: list[StampedEvent | LiveGap] = []

    async def slow_consumer() -> None:
        async for item in tail.subscribe(after_seq=0):
            received.append(item)
            await asyncio.Event().wait()

    with caplog.at_level(logging.ERROR), structlog.testing.capture_logs() as logs:
        task = asyncio.create_task(slow_consumer())
        await asyncio.sleep(0)
        for seq in range(1, tail.queue_capacity + tail.overflow_threshold + 4):
            tail.on_event(_stamped(seq))
        await asyncio.sleep(0)
        assert tail.evicted == 1
        assert tail.subscriber_count == 0
        assert any(entry.get("event") == "live_tail_subscriber_evicted" for entry in logs)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
