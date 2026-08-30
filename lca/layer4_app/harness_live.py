from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.agent import (
    ApprovalResumePoint,
    ContextMessage,
    LiveAgentRecovery,
    LiveAgentStatus,
    MessageReceipt,
    UserMessage,
)
from lca.contracts.harness.events import (
    ApprovalPersisted,
    ApprovalResolved,
    MessageAccepted,
    TurnEnded,
    TurnStarted,
)
from lca.contracts.protocols.session_turn import SessionFollowupPolicy, SessionTurnController
from lca.harness.agent.followup_policy import EnqueueFollowupPolicy
from lca.harness.session.inbox import Inbox
from lca.harness.session.resume_point import (
    resume_point_to_state_snapshot,
    serialize_resume_point,
)
from lca.harness.session.store import SessionStore
from lca.layer4_app.api import Agent
from lca.layer4_app.followup_dispatch import FollowupTurnDispatcher
from lca.layer4_app.live_session_state import (
    resume_point_from_result,
    status_from_task,
    turn_end_reason,
)

ResultT = TypeVar("ResultT")


class CognitiveLiveAgent:
    """Own one Session's lifecycle facts around profile-selected loop resources."""

    def __init__(
        self,
        agent: Agent,
        store: SessionStore,
        inbox: Inbox,
        *,
        identity_id: str,
        turn_controller: SessionTurnController,
        followup_policy: SessionFollowupPolicy | None = None,
    ) -> None:
        self._agent = agent
        self._store = store
        self._inbox = inbox
        self._id = identity_id
        self._turn_controller = turn_controller
        self._followup_policy = followup_policy or EnqueueFollowupPolicy()
        self._status = LiveAgentStatus.IDLE
        self._turn = 0
        self._idle = asyncio.Event()
        self._idle.set()
        self._cancelled = False
        self._cancel_keep_inbox = True
        self._turn_in_progress = False
        self._pending_resume: ApprovalResumePoint | None = None
        self._followup_dispatcher = FollowupTurnDispatcher(
            inbox=self._inbox,
            policy=self._followup_policy,
            session_id=self.session_id,
            run_turn=self._run_turn,
            may_continue=self._may_continue_followups,
            on_idle=self._idle.set,
        )

    @property
    def id(self) -> str:
        return self._id

    @property
    def session_id(self) -> str:
        return self._store.header.id

    @property
    def status(self) -> LiveAgentStatus:
        return self._status

    def restore(self, recovery: LiveAgentRecovery) -> None:
        self._status = recovery.status
        self._turn = recovery.completed_turns
        self._pending_resume = recovery.pending_resume
        self._cancelled = recovery.status is LiveAgentStatus.DISPOSED
        self._turn_in_progress = False
        if recovery.status is LiveAgentStatus.WORKING:
            raise ValueError("a working LiveAgent cannot be restored from a checkpoint")
        self._idle.set()

    async def followup(self, message: UserMessage) -> MessageReceipt:
        self._ensure_accepting_input()
        mid = message.message_id or new_id("msg")
        msg = UserMessage(content=message.content, role=message.role, message_id=mid)
        return await self._followup_dispatcher.followup(
            msg,
            turn_active=self._turn_controller.is_running,
        )

    async def resume_approval(
        self,
        approval_id: str,
        payload: str,
        *,
        idempotency_key: str,
    ) -> MessageReceipt:
        point = self._pending_resume
        if self._status is not LiveAgentStatus.WAITING_INPUT or point is None:
            raise ValueError("session has no approval awaiting a resume command")
        if point.approval_id != approval_id:
            raise ValueError("resume command does not match the pending approval")
        if not payload.strip():
            raise ValueError("approval resume payload must not be empty")

        self._idle.clear()
        self._status = LiveAgentStatus.WORKING
        self._turn_in_progress = True
        await self._store.append(
            ApprovalResolved(
                approval_id=approval_id,
                command_id=idempotency_key,
                payload=payload,
                approved=True,
            ),
            actor="user",
        )
        result = await self._run_operation(
            lambda: self._agent.resume(resume_point_to_state_snapshot(point), input=payload)
        )
        return await self._record_result(new_id("msg"), result)

    async def steer(self, message: UserMessage) -> MessageReceipt:
        self._ensure_accepting_input()
        mid = message.message_id or new_id("msg")
        msg = UserMessage(content=message.content, role=message.role, message_id=mid)
        event = await self._inbox.steer(msg)
        if self._status is LiveAgentStatus.IDLE and not self._followup_dispatcher.is_draining:
            claimed = await self._inbox.claim_next_step()
            if claimed:
                return await self._run_turn(claimed[0])
        return MessageReceipt(message_id=mid, session_id=self.session_id, seq=event.seq)

    async def inject(self, message: ContextMessage) -> MessageReceipt:
        self._ensure_accepting_input()
        mid = message.message_id or new_id("msg")
        event = await self._inbox.inject(
            UserMessage(content=message.content, role="system", message_id=mid)
        )
        return MessageReceipt(message_id=mid, session_id=self.session_id, seq=event.seq)

    async def cancel(self, reason: str = "user", *, keep_inbox: bool = True) -> None:
        del reason
        self._cancel_keep_inbox = keep_inbox
        await self._turn_controller.cancel()
        await self._record_cancellation(keep_inbox=keep_inbox)

    async def when_idle(self) -> None:
        await self._turn_controller.when_idle()
        await self._idle.wait()

    async def _run_turn(self, message: UserMessage) -> MessageReceipt:
        self._idle.clear()
        self._status = LiveAgentStatus.WORKING
        self._turn += 1
        await self._store.append(
            MessageAccepted(
                message_id=message.message_id,
                role=message.role,
                content_ref=message.content,
            ),
            actor="user",
        )
        await self._store.append(TurnStarted(turn=self._turn))
        self._turn_in_progress = True
        result = await self._run_operation(lambda: self._agent.run(message.content))
        return await self._record_result(message.message_id, result)

    async def _run_operation(self, operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
        try:
            return await self._turn_controller.run(operation)
        except asyncio.CancelledError:
            await self._record_cancellation(keep_inbox=self._cancel_keep_inbox)
            raise

    async def _record_result(self, message_id: str, result: object) -> MessageReceipt:
        status = getattr(result, "status", None)


        live_status = status_from_task(status)
        pending = (
            resume_point_from_result(result)
            if live_status is LiveAgentStatus.WAITING_INPUT
            else None
        )
        reason = turn_end_reason(status, live_status)

        await self._store.append(TurnEnded(turn=self._turn, reason=reason))
        if pending is not None:
            await self._store.append(
                ApprovalPersisted(
                    approval_id=pending.approval_id,
                    resume_point=serialize_resume_point(pending),
                )
            )
        # ADR-0099 retired the per-turn ``SessionCheckpoint`` event;
        # the journal's terminal event (``AgentRunFinished`` /
        # ``TeamRunFinished``) is the sole canonical signal.
        self._turn_in_progress = False
        self._pending_resume = pending
        self._status = live_status
        if (
            self._status is not LiveAgentStatus.WORKING
            and not self._followup_dispatcher.is_draining
        ):
            self._idle.set()
        return MessageReceipt(
            message_id=message_id,
            session_id=self.session_id,
            seq=self._store.current_seq,
        )

    async def _record_cancellation(self, *, keep_inbox: bool) -> None:
        """Commit one idempotent canceled checkpoint after task settlement."""

        if self._status is LiveAgentStatus.DISPOSED:
            if not keep_inbox:
                await self._inbox.clear()
            return
        if self._turn_in_progress:
            await self._store.append(TurnEnded(turn=self._turn, reason="canceled"))
            self._turn_in_progress = False
        self._cancelled = True
        self._pending_resume = None
        self._status = LiveAgentStatus.DISPOSED
        if not keep_inbox:
            await self._inbox.clear()
        # ADR-0099 retired the cancellation SessionCheckpoint event.
        self._idle.set()

    def _may_continue_followups(self) -> bool:
        return (
            self._status is LiveAgentStatus.IDLE
            and not self._cancelled
            and not self._turn_controller.is_running
        )

    def _ensure_accepting_input(self) -> None:
        if self._cancelled or self._status is LiveAgentStatus.DISPOSED:
            raise ValueError("disposed session does not accept input")
        if self._status is LiveAgentStatus.WAITING_INPUT:
            raise ValueError("approval waiting input requires an explicit resume command")
