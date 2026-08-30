"""Concurrent follow-up admission and FIFO draining for one live Session."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from lca.contracts.harness.collaboration.agent import MessageReceipt, UserMessage
from lca.contracts.protocols.session.session_turn import (
    FollowupDispatch,
    SessionFollowupPolicy,
    TurnAlreadyRunningError,
)
from lca.harness.session.inbox import Inbox


class FollowupTurnDispatcher:
    """Serialize policy-governed follow-ups without owning Session lifecycle facts.

    The owner supplies the concrete turn operation and observes its own status.
    This component only protects the small admission/next-claim critical section
    required to preserve FIFO order when a new follow-up arrives as a drain is
    about to become idle.
    """

    def __init__(
        self,
        *,
        inbox: Inbox,
        policy: SessionFollowupPolicy,
        session_id: str,
        run_turn: Callable[[UserMessage], Awaitable[MessageReceipt]],
        may_continue: Callable[[], bool],
        on_idle: Callable[[], None],
    ) -> None:
        self._inbox = inbox
        self._policy = policy
        self._session_id = session_id
        self._run_turn = run_turn
        self._may_continue = may_continue
        self._on_idle = on_idle
        self._draining = False
        self._lock = asyncio.Lock()

    @property
    def is_draining(self) -> bool:
        """Return whether an admitted follow-up chain currently owns dispatch."""

        return self._draining

    async def followup(self, message: UserMessage, *, turn_active: bool) -> MessageReceipt:
        """Persist one message, then start, enqueue, or reject it deterministically."""

        async with self._lock:
            dispatch = self._policy.decide(turn_active=turn_active or self._draining)
            if dispatch is FollowupDispatch.REJECT:
                raise TurnAlreadyRunningError(
                    f"session {self._session_id!r} already has an active turn"
                )
            if dispatch not in {FollowupDispatch.START, FollowupDispatch.ENQUEUE}:
                raise ValueError(f"unsupported follow-up dispatch: {dispatch!r}")
            event = await self._inbox.followup(message)
            if dispatch is FollowupDispatch.ENQUEUE:
                return MessageReceipt(
                    message_id=message.message_id,
                    session_id=self._session_id,
                    seq=event.seq,
                )
            current = await self._inbox.claim_one_next_turn()
            if current is None:
                raise RuntimeError("admitted follow-up was not available in the durable inbox")
            self._draining = True
        return await self._drain(current)

    async def _drain(self, first_message: UserMessage) -> MessageReceipt:
        first_receipt: MessageReceipt | None = None
        try:
            current: UserMessage | None = first_message
            while current is not None:
                receipt = await self._run_turn(current)
                if first_receipt is None:
                    first_receipt = receipt
                if not self._may_continue():
                    break
                async with self._lock:
                    current = await self._inbox.claim_one_next_turn()
                    if current is None:
                        self._draining = False
                        self._on_idle()
            if first_receipt is None:
                raise RuntimeError("follow-up drain did not execute its admitted message")
            return first_receipt
        finally:
            async with self._lock:
                self._draining = False
                if self._may_continue():
                    self._on_idle()


__all__ = ["FollowupTurnDispatcher"]
