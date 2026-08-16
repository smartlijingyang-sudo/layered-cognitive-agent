"""SSE watermark alignment (spec §B.8)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.harness.projection import ProjectionChange, ProjectionSnapshot


class SSEAligner:
    """Replay missed ProjectionChange values from last_seq, then subscribe live."""

    def __init__(self, projection_registry: Any) -> None:
        self._registry = projection_registry

    async def subscribe_with_reconnect(
        self, session_id: str, last_seq: int
    ) -> AsyncIterator[ProjectionChange]:
        snapshot: ProjectionSnapshot = self._registry.snapshot(session_id)
        current_seq = snapshot.as_of_seq
        if last_seq < current_seq:
            for key, value in snapshot.values.items():
                yield ProjectionChange(
                    session_id=session_id,
                    key=key,
                    version=1,
                    seq=current_seq,
                    value=value,
                )

        queue: asyncio.Queue[ProjectionChange] = asyncio.Queue()

        def listener(change: ProjectionChange) -> None:
            if change.session_id == session_id and change.seq > current_seq:
                queue.put_nowait(change)

        self._registry.subscribe_changes(listener)
        while True:
            change = await queue.get()
            yield change
