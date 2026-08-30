"""Session-scoped ownership and dispatch of Agent turns.

The Session Spine owns durable facts. Profile-selected implementations own
process-local turn execution and choose what happens when a follow-up arrives
while the Session is already advancing. Keeping task ownership and admission
policy as separate seams allows a deployment to replace concurrency behavior
without coupling command routing or a concrete Agent Loop to one strategy.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Protocol, TypeVar, runtime_checkable

ResultT = TypeVar("ResultT")


class TurnAlreadyRunningError(RuntimeError):
    """Raised when a Session attempts to advance more than one turn at once."""


class FollowupDispatch(StrEnum):
    """The only valid outcomes for one Session follow-up admission decision."""

    START = "start"
    ENQUEUE = "enqueue"
    REJECT = "reject"


@runtime_checkable
class SessionFollowupPolicy(Protocol):
    """Choose a safe admission outcome for a user follow-up.

    Policies are deliberately pure.  They only decide whether a message starts
    a new turn, waits in the existing FIFO inbox, or is rejected; the
    ``CognitiveLiveAgent`` remains the sole owner of Journal facts, turn
    lifecycle transitions, and the profile-selected task controller.
    """

    def decide(self, *, turn_active: bool) -> FollowupDispatch: ...


@runtime_checkable
class SessionTurnController(Protocol):
    """Own one in-flight turn task for a single durable Session.

    Implementations must serialize ``run`` calls, propagate cancellation to the
    owned task, and make ``when_idle`` wait until task cleanup has completed.
    They do not own Journal facts or Agent state; the selected LiveAgent records
    those through the existing SessionStore and Reducer paths.
    """

    @property
    def is_running(self) -> bool: ...

    async def run(self, operation: Callable[[], Awaitable[ResultT]]) -> ResultT: ...

    async def cancel(self) -> bool: ...

    async def when_idle(self) -> None: ...


@runtime_checkable
class SessionTurnControllerFactory(Protocol):
    """Create an isolated task controller for one live Session owner."""

    def create(self, *, session_id: str) -> SessionTurnController: ...


__all__ = [
    "FollowupDispatch",
    "SessionFollowupPolicy",
    "SessionTurnController",
    "SessionTurnControllerFactory",
    "TurnAlreadyRunningError",
]
