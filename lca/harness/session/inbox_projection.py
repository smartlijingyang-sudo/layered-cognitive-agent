"""Pure projection of durable inbox facts into pending message state.

The projection owns only replay and wire-payload conversion.  Inbox remains the
mutation coordinator: it appends facts and claims messages through SessionStore.
Keeping these responsibilities separate makes recovery testable without a live
store and prevents persistence concerns from leaking into the projection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from lca.contracts.harness.agent import UserMessage
from lca.contracts.harness.session import SessionEvent

InboxTarget = Literal["next_turn", "next_step"]


@dataclass
class InboxState:
    """The current unclaimed messages for the two delivery boundaries."""

    next_turn: list[UserMessage] = field(default_factory=list)
    next_step: list[UserMessage] = field(default_factory=list)


class InboxProjector:
    """Replay inbox facts and translate messages at the journal seam."""

    @classmethod
    def recover(cls, events: tuple[SessionEvent, ...]) -> InboxState:
        """Rebuild pending queues from the append/remove fact stream."""

        state = InboxState()
        for event in events:
            if event.type != "inbox.spliced.v1":
                continue
            target = event.data.get("target")
            if target not in {"next_turn", "next_step"}:
                continue
            queue = state.next_turn if target == "next_turn" else state.next_step
            if event.data.get("op") == "append":
                queue.extend(cls._messages_from_event(event))
            elif event.data.get("op") == "remove":
                removed = set(cls._message_ids(event))
                queue[:] = [message for message in queue if message.message_id not in removed]
        return state

    @staticmethod
    def message_payload(message: UserMessage) -> dict[str, str]:
        """Convert a domain message to the compact journal payload."""

        return {
            "content": message.content,
            "role": message.role,
            "message_id": message.message_id,
        }

    @staticmethod
    def _messages_from_event(event: SessionEvent) -> tuple[UserMessage, ...]:
        raw_messages = event.data.get("messages")
        if not isinstance(raw_messages, (list, tuple)):
            return ()
        messages: list[UserMessage] = []
        for raw in raw_messages:
            if not isinstance(raw, dict):
                continue
            content = raw.get("content")
            role = raw.get("role")
            message_id = raw.get("message_id")
            if (
                isinstance(content, str)
                and isinstance(role, str)
                and isinstance(message_id, str)
                and message_id
            ):
                messages.append(UserMessage(content=content, role=role, message_id=message_id))
        return tuple(messages)

    @staticmethod
    def _message_ids(event: SessionEvent) -> tuple[str, ...]:
        raw_ids = event.data.get("message_ids")
        if not isinstance(raw_ids, (list, tuple)):
            return ()
        return tuple(value for value in raw_ids if isinstance(value, str))


__all__ = ["InboxProjector", "InboxState", "InboxTarget"]
