"""Room runtime dispatcher (room runtime go-live M1 + Phase 2).

Turns a room message into a real run dispatch: append the USER fact, route
through ``RoomMessageRouter``, start a run via the injected ``RunStarter``,
and record the RUN_STARTED fact. ``finalize`` is the entry point for folding
results to be written back into the room transcript. ``sync_completed``
appends FOLDED facts for runs that reached a terminal state after the fact
(lazy revival: the transcript is consistent whenever it is read).
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

TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "error", "canceled", "cancelled", "interrupted", "timeout"}
)
"""Run statuses that end a collaboration round and justify a FOLDED fact."""


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


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """Terminal outcome of a room-dispatched run, read after the fact."""

    status: str
    error: str = ""
    output: str = ""


class RunStarter(Protocol):
    """Protocol for starting a real LCA run from a room message."""

    async def __call__(
        self,
        *,
        objective: str,
        mode: str,
        correlation_id: str,
    ) -> RunDispatchResult: ...


class RunStatusReader(Protocol):
    """Protocol for reading a run's terminal outcome by ``run_id``."""

    async def __call__(self, run_id: str) -> RunOutcome: ...


class _NullRunStatusReader:
    """Default reader: never reports a terminal state (no revival without wiring)."""

    async def __call__(self, run_id: str) -> RunOutcome:
        del run_id
        return RunOutcome(status="unknown")


class RoomDispatcher:
    """Orchestrates room message ingestion, run dispatch, and lazy revival."""

    def __init__(
        self,
        room_repository: RoomRepository,
        message_store: RoomMessageStore,
        run_starter: RunStarter,
        clock: Callable[[], float] | None = None,
        run_status_reader: RunStatusReader | None = None,
    ) -> None:
        self._room_repository = room_repository
        self._message_store = message_store
        self._run_starter = run_starter
        self._clock = clock or time.time
        self._run_status_reader = run_status_reader or _NullRunStatusReader()

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

        correlation_id = self._correlation_id_for_run(room_id, run_id)
        folded_msg = RoomMessage(
            message_id=new_id("room_msg"),
            room_id=room_id,
            kind=RoomMessageKind.FOLDED,
            sender_id=room.coordinator_agent_id,
            content=folded.synthesized_verdict,
            correlation_id=correlation_id,
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

    async def sync_completed(self, room_id: str) -> tuple[RoomMessage, ...]:
        """Append FOLDED facts for room runs that reached a terminal state.

        Idempotent: a correlation_id that already has a FOLDED fact is skipped.
        Runs still in flight (or unknown) are left untouched for a later read.
        """
        messages = self._message_store.list_messages(room_id)
        started_by_corr: dict[str, RoomMessage] = {}
        folded_corrs: set[str] = set()
        for msg in messages:
            if msg.kind == RoomMessageKind.RUN_STARTED and msg.correlation_id:
                started_by_corr.setdefault(msg.correlation_id, msg)
            elif msg.kind == RoomMessageKind.FOLDED and msg.correlation_id:
                folded_corrs.add(msg.correlation_id)

        appended: list[RoomMessage] = []
        for corr, started in started_by_corr.items():
            if corr in folded_corrs:
                continue
            outcome = await self._run_status_reader(started.run_id)
            if outcome.status not in TERMINAL_STATUSES:
                continue
            appended.append(await self._finalize_from_outcome(started, outcome))
        return tuple(appended)

    async def _finalize_from_outcome(
        self,
        started: RoomMessage,
        outcome: RunOutcome,
    ) -> RoomMessage:
        """Build and append a FOLDED fact from a run's terminal outcome."""
        completed = outcome.status == "completed"
        if completed and outcome.output:
            verdict = outcome.output
        elif completed:
            verdict = f"run {started.run_id} 已完成"
        else:
            verdict = f"run {started.run_id} 结束: {outcome.error or outcome.status}"
        folded = PeerFoldedResult(
            task_id=started.correlation_id,
            synthesized_verdict=verdict,
            member_findings={},
            consensus_status="unanimous" if completed else "concerns_noted",
            member_metadata={},
        )
        return await self.finalize(started.room_id, started.run_id, folded)

    def _correlation_id_for_run(self, room_id: str, run_id: str) -> str:
        """Recover a round's correlation_id from its RUN_STARTED fact."""
        for msg in self._message_store.list_messages(room_id):
            if msg.kind == RoomMessageKind.RUN_STARTED and msg.run_id == run_id:
                return msg.correlation_id
        return ""


__all__ = [
    "TERMINAL_STATUSES",
    "RoomDispatcher",
    "RoomNotFoundError",
    "RunDispatchResult",
    "RunOutcome",
    "RunStarter",
    "RunStatusReader",
]
