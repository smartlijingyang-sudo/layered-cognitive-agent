"""Durable inbox mutation coordinator for one Session."""

from __future__ import annotations

from lca.contracts.harness.agent import UserMessage
from lca.contracts.harness.events import InboxSpliced
from lca.contracts.harness.session import SessionEvent
from lca.harness.session.inbox_projection import InboxProjector, InboxState, InboxTarget
from lca.harness.session.store import SessionStore


class Inbox:
    """Queue follow-ups and steering messages through the Session Journal.

    ``Inbox`` owns mutation and claim semantics only.  Replay and journal
    payload conversion live in :class:`InboxProjector`, so recovery can be
    tested through a pure interface without constructing a live inbox store.
    """

    def __init__(self, store: SessionStore) -> None:
        self._store = store
        self._state = InboxProjector.recover(store.events())

    @property
    def state(self) -> InboxState:
        return self._state

    async def followup(self, msg: UserMessage) -> SessionEvent:
        return await self._append("next_turn", msg, actor="user")

    async def steer(self, msg: UserMessage) -> SessionEvent:
        return await self._append("next_step", msg, actor="user")

    async def inject(self, msg: UserMessage) -> SessionEvent:
        return await self._append("next_step", msg, actor="system")

    async def claim_next_turn(self) -> list[UserMessage] | None:
        return await self._claim("next_turn")

    async def claim_one_next_turn(self) -> UserMessage | None:
        """Claim exactly one FIFO follow-up without disturbing a concurrent tail."""

        return await self._claim_one("next_turn")

    async def claim_next_step(self) -> list[UserMessage] | None:
        return await self._claim("next_step")

    async def clear(self) -> None:
        """Durably remove all pending messages from both queues."""

        await self._claim("next_turn")
        await self._claim("next_step")

    async def _append(
        self,
        target: InboxTarget,
        msg: UserMessage,
        *,
        actor: str,
    ) -> SessionEvent:
        self._queue(target).append(msg)
        return await self._store.append(
            InboxSpliced(
                op="append",
                target=target,
                message_ids=(msg.message_id,),
                messages=(InboxProjector.message_payload(msg),),
            ),
            actor=actor,
        )

    async def _claim_one(self, target: InboxTarget) -> UserMessage | None:
        queue = self._queue(target)
        if not queue:
            return None
        message = queue.pop(0)
        await self._store.append(
            InboxSpliced(op="remove", target=target, message_ids=(message.message_id,)),
            actor="system",
        )
        return message

    async def _claim(self, target: InboxTarget) -> list[UserMessage] | None:
        queue = self._queue(target)
        if not queue:
            return None
        messages = list(queue)
        queue.clear()
        await self._store.append(
            InboxSpliced(
                op="remove",
                target=target,
                message_ids=tuple(message.message_id for message in messages),
            ),
            actor="system",
        )
        return messages

    def _queue(self, target: InboxTarget) -> list[UserMessage]:
        return self._state.next_turn if target == "next_turn" else self._state.next_step


__all__ = ["Inbox", "InboxState"]
