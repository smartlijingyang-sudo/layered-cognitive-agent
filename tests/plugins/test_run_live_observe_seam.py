"""Run live observe seam tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lca.contracts.models.observability.journal.journal import (
    ReasoningDelta,
    RunScope,
    StampedEvent,
)
from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.plugins.observability.run.ledger_seam import FilesystemRunLedgerFactory
from lca.plugins.transport.run_live_observe__seam import RunLiveObserveSeam


class _FakeSession:
    def __init__(self, tail: LiveTail) -> None:
        self.tail = tail
        self.hub = None
        self.status = RunLifecycleStatus.RUNNING
        self.error = ""


@pytest.mark.asyncio
async def test_observe_seam_streams_reasoning_from_shared_tail() -> None:
    tail = LiveTail()
    session = _FakeSession(tail)
    seam = RunLiveObserveSeam()

    async def _produce() -> None:
        await asyncio.sleep(0.01)
        tail.on_event(
            StampedEvent(
                seq=1,
                ts=0.0,
                scope=RunScope(run_id="r1"),
                event=ReasoningDelta(step=1, text_delta="think", seq=1),
                event_type="ReasoningDelta",
            )
        )
        tail.close()

    producer = asyncio.create_task(_produce())
    frames: list[bytes] = []
    async for line in seam.stream(session, after=0):
        frames.append(line)
    await producer

    assert any(b"event: reasoning" in frame for frame in frames)


def test_ledger_factory_uses_single_live_tail_ssot(tmp_path: Path) -> None:
    factory = FilesystemRunLedgerFactory(root=tmp_path, fsync_each_append=False)
    components = factory.create_run_components(spine_path=tmp_path / "r1" / "run.spine.jsonl")
    assert components.writer is components.tail
