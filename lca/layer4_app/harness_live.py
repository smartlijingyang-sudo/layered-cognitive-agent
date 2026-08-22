"""Wrap the public Agent facade as a LiveAgent over SessionStore + Inbox."""

from __future__ import annotations

import asyncio

from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.agent import (
    ContextMessage,
    MessageReceipt,
    UserMessage,
)
from lca.contracts.harness.events import (
    MessageAccepted,
    SessionCheckpoint,
    ToolApprovalResolved,
    TurnEnded,
    TurnStarted,
)
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.harness.session.inbox import Inbox
from lca.harness.session.store import SessionStore
from lca.layer4_app.api import Agent


def _status_from_task(status: TaskStatus) -> str:
    if status == TaskStatus.INPUT_REQUIRED:
        return "waiting_input"
    if status == TaskStatus.COMPLETED:
        return "idle"
    if status == TaskStatus.FAILED:
        return "idle"
    if status == TaskStatus.CANCELED:
        return "disposed"
    return "working"


class CognitiveLiveAgent:
    """LiveAgent adapter around the existing Agent facade."""

    def __init__(
        self,
        agent: Agent,
        store: SessionStore,
        inbox: Inbox,
        *,
        identity_id: str,
    ) -> None:
        self._agent = agent
        self._store = store
        self._inbox = inbox
        self._id = identity_id
        self._status = "idle"
        self._turn = 0
        self._idle = asyncio.Event()
        self._idle.set()
        self._cancelled = False
        self._last_result: object | None = None

    @property
    def id(self) -> str:
        return self._id

    @property
    def session_id(self) -> str:
        return self._store.header.id

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_result(self) -> object | None:
        return self._last_result

    async def followup(self, message: UserMessage) -> MessageReceipt:
        mid = message.message_id or new_id("msg")
        msg = UserMessage(content=message.content, role=message.role, message_id=mid)
        await self._inbox.followup(msg)
        claimed = self._inbox.claim_next_turn() or [msg]
        return await self._run_turn(claimed[0], wake=True)

    async def steer(self, message: UserMessage) -> MessageReceipt:
        mid = message.message_id or new_id("msg")
        msg = UserMessage(content=message.content, role=message.role, message_id=mid)
        await self._inbox.steer(msg)
        if self._status == "idle":
            claimed = self._inbox.claim_next_step() or [msg]
            return await self._run_turn(claimed[0], wake=True)
        event = await self._store.append(
            MessageAccepted(message_id=mid, role="user", content_ref=msg.content)
        )
        return MessageReceipt(message_id=mid, session_id=self.session_id, seq=event.seq)

    async def inject(self, message: ContextMessage) -> MessageReceipt:
        mid = message.message_id or new_id("msg")
        await self._inbox.inject(
            UserMessage(content=message.content, role="system", message_id=mid)
        )
        event = await self._store.append(
            MessageAccepted(message_id=mid, role="system", content_ref=message.content)
        )
        return MessageReceipt(message_id=mid, session_id=self.session_id, seq=event.seq)

    def cancel(self, reason: str = "user", *, keep_inbox: bool = True) -> None:
        self._cancelled = True
        self._status = "disposed"
        if not keep_inbox:
            self._inbox.state.next_turn.clear()
            self._inbox.state.next_step.clear()
        self._idle.set()

    async def when_idle(self) -> None:
        await self._idle.wait()

    async def answer(self, text: str) -> MessageReceipt:
        await self._store.append(
            ToolApprovalResolved(call_id=text, decision="approved"), actor="user"
        )
        mid = new_id("msg")
        if self._last_result is not None:
            extra = getattr(self._last_result, "extra", {}) or {}
            checkpoint = extra.get("declarative_checkpoint")
            if checkpoint is not None:
                result = await self._agent.resume(checkpoint, input=text)
                return await self._record_result(mid, text, result)
        return await self.followup(UserMessage(content=text, message_id=mid))

    async def _run_turn(self, message: UserMessage, *, wake: bool) -> MessageReceipt:
        self._idle.clear()
        self._status = "working"
        self._turn += 1
        accepted = await self._store.append(
            MessageAccepted(
                message_id=message.message_id,
                role=message.role,
                content_ref=message.content,
            ),
            actor="user",
        )
        await self._store.append(TurnStarted(turn=self._turn))
        result = await self._agent.run(message.content)
        receipt = await self._record_result(message.message_id, message.content, result)
        receipt = MessageReceipt(
            message_id=message.message_id,
            session_id=self.session_id,
            seq=accepted.seq,
        )
        return receipt

    async def _record_result(self, message_id: str, content: str, result: object) -> MessageReceipt:
        self._last_result = result
        status = getattr(result, "status", None)
        output = getattr(result, "output", None)
        error = getattr(result, "error", None)
        live_status = _status_from_task(status) if status is not None else "idle"
        reason = (
            "waiting_input"
            if live_status == "waiting_input"
            else ("error" if getattr(status, "value", "") == TaskStatus.FAILED else "completed")
        )
        if status == TaskStatus.FAILED:
            reason = "error"
        await self._store.append(TurnEnded(turn=self._turn, reason=reason))
        await self._store.append(
            SessionCheckpoint(
                status=live_status if live_status != "idle" else "completed",
                snapshot_ref=None,
                answer=output if isinstance(output, str) else None,
                error=error if isinstance(error, str) else None,
            )
        )
        self._status = live_status
        if self._status != TaskStatus.WORKING:
            self._idle.set()
        return MessageReceipt(
            message_id=message_id, session_id=self.session_id, seq=self._store.current_seq
        )
