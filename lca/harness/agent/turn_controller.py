"""Default in-process controller for one Session Spine turn task."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import TypeVar, cast

from lca.contracts.protocols.session.session_turn import (
    SessionTurnController,
    TurnAlreadyRunningError,
)

ResultT = TypeVar("ResultT")


async def _await_operation(operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
    """Bridge the protocol's generic Awaitable into create_task's coroutine input."""

    return await operation()


class InProcessSessionTurnController(SessionTurnController):
    """Own the single process-local task allowed to advance one Session.

    The controller deliberately owns only ephemeral task lifecycle.  The caller
    remains responsible for durable turn facts, checkpoints, and state updates.
    This split allows a profile to substitute a remote or durable task controller
    without changing the LiveAgent protocol or the Gateway command surface.
    """

    def __init__(self, *, session_id: str) -> None:
        self._session_id = session_id
        self._active: asyncio.Task[object] | None = None
        self._idle = asyncio.Event()
        self._idle.set()
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        """Return whether this Session currently owns an advancing turn task."""

        task = self._active
        return task is not None and not task.done()

    async def run(self, operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
        """Run exactly one turn operation, rejecting concurrent Session turns."""

        async with self._lock:
            if self.is_running:
                raise TurnAlreadyRunningError(
                    f"session {self._session_id!r} already has an active turn"
                )
            self._idle.clear()
            task: asyncio.Task[ResultT] = asyncio.create_task(_await_operation(operation))
            self._active = cast("asyncio.Task[object]", task)

        try:
            return await task
        finally:
            async with self._lock:
                if self._active is task:
                    self._active = None
                    self._idle.set()

    async def cancel(self) -> bool:
        """Request cancellation and wait until the active task has settled."""

        async with self._lock:
            task = self._active
            if task is None or task.done():
                return False
            task.cancel()

        with suppress(asyncio.CancelledError):
            await task
        return True

    async def when_idle(self) -> None:
        """Wait until no turn task remains owned by this Session."""

        await self._idle.wait()


__all__ = ["InProcessSessionTurnController"]
