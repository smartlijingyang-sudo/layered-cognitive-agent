"""Durable dual-queue inbox (spec §3.6.1)."""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.harness.agent import UserMessage
from lca.contracts.harness.events import InboxSpliced
from lca.harness.session.store import SessionStore


@dataclass
class InboxState:
    next_turn: list[UserMessage] = field(default_factory=list)
    next_step: list[UserMessage] = field(default_factory=list)


class Inbox:
    """Two queues: followup opens a turn; steer/inject land on the next step."""

    def __init__(self, store: SessionStore) -> None:
        self._store = store
        self._state = InboxState()

    @property
    def state(self) -> InboxState:
        return self._state

    async def followup(self, msg: UserMessage) -> None:
        self._state.next_turn.append(msg)
        await self._store.append(
            InboxSpliced(op="append", target="next_turn", message_ids=(msg.message_id,)),
            actor="user",
        )

    async def steer(self, msg: UserMessage) -> None:
        self._state.next_step.append(msg)
        await self._store.append(
            InboxSpliced(op="append", target="next_step", message_ids=(msg.message_id,)),
            actor="user",
        )

    async def inject(self, msg: UserMessage) -> None:
        self._state.next_step.append(msg)
        await self._store.append(
            InboxSpliced(op="append", target="next_step", message_ids=(msg.message_id,)),
            actor="system",
        )

    def claim_next_turn(self) -> list[UserMessage] | None:
        if not self._state.next_turn:
            return None
        msgs = list(self._state.next_turn)
        self._state.next_turn.clear()
        return msgs

    def claim_next_step(self) -> list[UserMessage] | None:
        if not self._state.next_step:
            return None
        msgs = list(self._state.next_step)
        self._state.next_step.clear()
        return msgs
