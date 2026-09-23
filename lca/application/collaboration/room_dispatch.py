"""Room runtime dispatcher (room runtime go-live M1).

Turns a room message into a real run dispatch: append the USER fact, route
through ``RoomMessageRouter``, start a run via the injected ``RunStarter``,
and record the RUN_STARTED fact. ``finalize`` is the entry point for folding
results to be written back into the room transcript.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.collaboration.peer import (
    PeerFoldedResult,
    RoomMessage,
    RoomMessageKind,
)
from lca.domain.collaboration.room import (
    RoomMessageRouter,
    RoomMessageStore,
    RoomRepository,
)


class RoomNotFoundError(Exception):
    """Raised when a dispatch/finalize targets an unknown room."""

    def __init__(self, room_id: str) -> None:
        super().__init__(f"room not found: {room_id}")
        self.room_id = room_id


@dataclass(frozen=True, slots=True)
class RunDispatchResult:
    """Stable receipt returned by a ``RunStarter``."""

    run_id: str
    trace_id: str
    accepted: bool
    rejection_reason: str | None = None


class RunStarter(Protocol):
    """Protocol for starting a real LCA run from a room message."""

    async def __call__(
        self,
        *,
        objective: str,
        mode: str,
        correlation_id: str,
    ) -> RunDispatchResult: ...


class RoomDispatcher:
    """Orchestrates room message ingestion and run dispatch."""

    def __init__(
        self,
        room_repository: RoomRepository,
        message_store: RoomMessageStore,
        run_starter: RunStarter,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._room_repository = room_repository
        self._message_store = message_store
        self._run_starter = run_starter
        self._clock = clock or time.time

    async def dispatch(
        self,
        room_id: str,
        user_text: str,
        sender_id: str = "user",
    ) -> RoomMessage:
        """Append a USER message and dispatch a real run, returning RUN_STARTED."""
        room = self._room_repository.get(room_id)
        if room is None:
            raise RoomNotFoundError(room_id)

        user_msg = RoomMessage(
            message_id=new_id("room_msg"),
            room_id=room_id,
            kind=RoomMessageKind.USER,
            sender_id=sender_id,
            content=user_text,
            created_at_ms=int(self._clock() * 1000),
        )
        self._message_store.append(user_msg)

        selected = RoomMessageRouter(room).route_message(user_text)
        mode = "team" if room.member_peer_ids else "solo"
        correlation_id = new_id("room")
        result = await self._run_starter(
            objective=user_text,
            mode=mode,
            correlation_id=correlation_id,
        )

        started_msg = RoomMessage(
            message_id=new_id("room_msg"),
            room_id=room_id,
            kind=RoomMessageKind.RUN_STARTED,
            sender_id=room.coordinator_agent_id,
            content=f"已启动 run {result.run_id}",
            correlation_id=correlation_id,
            run_id=result.run_id,
            payload={
                "trace_id": result.trace_id,
                "selected_peers": list(selected),
                "accepted": result.accepted,
                "rejection_reason": result.rejection_reason,
            },
            created_at_ms=int(self._clock() * 1000),
        )
        self._message_store.append(started_msg)
        return started_msg

    async def finalize(
        self,
        room_id: str,
        run_id: str,
        folded: PeerFoldedResult,
    ) -> RoomMessage:
        """Append a FOLDED message carrying the delegation fold result."""
        room = self._room_repository.get(room_id)
        if room is None:
            raise RoomNotFoundError(room_id)

        folded_msg = RoomMessage(
            message_id=new_id("room_msg"),
            room_id=room_id,
            kind=RoomMessageKind.FOLDED,
            sender_id=room.coordinator_agent_id,
            content=folded.synthesized_verdict,
            run_id=run_id,
            payload={
                "task_id": folded.task_id,
                "member_findings": folded.member_findings,
                "consensus_status": folded.consensus_status,
                "member_metadata": folded.member_metadata,
            },
            created_at_ms=int(self._clock() * 1000),
        )
        self._message_store.append(folded_msg)
        return folded_msg


__all__ = [
    "RoomDispatcher",
    "RoomNotFoundError",
    "RunDispatchResult",
    "RunStarter",
]
