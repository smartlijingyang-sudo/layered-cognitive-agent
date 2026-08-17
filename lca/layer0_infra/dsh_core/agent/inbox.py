"""1:1 port of ``@deepseek-ai/dsh-agent/inbox.ts``."""

from __future__ import annotations

import math
from typing import Any, Protocol

from lca.layer0_infra.dsh_core.agent.types import InboxTarget
from lca.layer0_infra.dsh_core.session._llm_types import MessageId, UserMessage
from lca.layer0_infra.dsh_core.session.types import SessionEvent, SessionId


class _InboxSession(Protocol):
    """Minimal session surface needed by Inbox."""

    @property
    def id(self) -> SessionId: ...

    @property
    def events(self) -> list[SessionEvent]: ...

    @property
    def header(self) -> Any: ...

    def append(self, event_type: str, data: dict[str, Any]) -> SessionEvent: ...


class InboxNotifications(Protocol):
    """Live notifications committed by inbox mutations."""

    def inserted(self, message: UserMessage) -> None:
        """Publish one inserted message."""
        ...

    def discarded(self, message: UserMessage) -> None:
        """Publish one discarded message."""
        ...

    def claimed(self, message: UserMessage, turn: int) -> None:
        """Publish one claimed message inside its owning turn."""
        ...


class Inbox:
    """A replay-once projection that incrementally consumes later inbox splices."""

    __slots__ = ("_notifications", "_session", "_state")

    def __init__(
        self,
        session: _InboxSession,
        notifications: InboxNotifications,
    ) -> None:
        self._session = session
        self._notifications = notifications
        self._state: dict[str, list[UserMessage]] = {
            "next-turn": [],
            "next-step": [],
        }
        header = session.header
        seed_length = (
            getattr(header, "seed_length", None) or getattr(header, "seedLength", None) or 0
        )
        for event in session.events[seed_length:]:
            if event.type != "agent/inbox/spliced":
                continue
            try:
                self._apply(event.data if isinstance(event.data, dict) else {})
            except Exception as exc:
                raise RuntimeError(
                    f"invalid persisted inbox splice at session seq {event.seq}"
                ) from exc

    # -- public read accessors ------------------------------------------------

    @property
    def next_turn(self) -> list[UserMessage]:
        """Prompts awaiting individual turns."""
        return self._state["next-turn"]

    @property
    def next_step(self) -> list[UserMessage]:
        """Input awaiting the next step boundary."""
        return self._state["next-step"]

    @property
    def has_pending(self) -> bool:
        """Whether either pending-message list contains work."""
        return len(self.next_turn) > 0 or len(self.next_step) > 0

    # -- mutations ------------------------------------------------------------

    def clear(self) -> None:
        """Durably cancel all pending input, clearing next-step before next-turn."""
        self.splice("next-step", 0, len(self.next_step), [])
        self.splice("next-turn", 0, len(self.next_turn), [])

    def claim(self, target: InboxTarget, turn: int) -> list[UserMessage]:
        """Remove and return the complete batch proposed for one step.

        Publishes each claimed message.  The durable splices are pure deletions.

        Args:
            target: whether this boundary also consumes one queued turn.
            turn: turn that will own the claimed batch.

        Returns:
            next-step input followed by the queued turn, when requested.

        .. note:: Internal — the agent loop's step-boundary operation, not a plugin extension point.
        """
        claimed_msgs = self._mutate("next-step", 0, len(self.next_step), [], discard_removed=False)
        if target == "next-turn":
            claimed_msgs.extend(self._mutate("next-turn", 0, 1, [], discard_removed=False))
        for message in claimed_msgs:
            self._notifications.claimed(message, turn)
        return claimed_msgs

    def append(self, target: InboxTarget, message: UserMessage) -> None:
        """Append one message to a pending list and durably record the insertion.

        Raises:
            RuntimeError: if the message identity is already pending.
        """
        self.splice(target, len(self._state[target]), 0, [message])

    def prepend(self, target: InboxTarget, message: UserMessage) -> None:
        """Prepend one message to a pending list and durably record the insertion.

        Raises:
            RuntimeError: if the message identity is already pending.
        """
        self.splice(target, 0, 0, [message])

    def replace(self, message_id: MessageId, new_message: UserMessage) -> bool:
        """Replace one pending message in place, possibly changing its identity.

        A successful replacement publishes the old message as discarded and the
        new message as inserted.

        Returns:
            Whether the message was still pending.

        Raises:
            RuntimeError: if the replacement duplicates another pending message identity.
        """
        location = self._locate(message_id)
        if location is None:
            return False
        self.splice(location[0], location[1], 1, [new_message])
        return True

    def remove(self, message_id: MessageId) -> bool:
        """Remove one pending message and durably record its cancellation.

        Returns:
            Whether the message was still pending.
        """
        location = self._locate(message_id)
        if location is None:
            return False
        self.splice(location[0], location[1], 1, [])
        return True

    def splice(
        self,
        target: InboxTarget,
        start: int,
        delete_count: int,
        inserted: list[UserMessage],
    ) -> list[UserMessage]:
        """Apply standard splice semantics and durably record the normalized result.

        The durable event commits before the live projection mutates, so
        synchronous ``session/event`` observers see the pre-splice lists and
        can reconstruct the removed messages from the normalized coordinates.

        Returns:
            Messages removed by the splice.
        """
        return self._mutate(target, start, delete_count, inserted, discard_removed=True)

    # -- private helpers ------------------------------------------------------

    def _locate(self, message_id: MessageId) -> tuple[InboxTarget, int] | None:
        """Locate one pending identity across both owned lists."""
        for target in ("next-turn", "next-step"):
            inbox = self._state[target]
            for i, message in enumerate(inbox):
                if message.id == message_id:
                    return (target, i)  # type: ignore[return-value]
        return None

    def _mutate(
        self,
        target: InboxTarget,
        start: int,
        delete_count: int,
        inserted: list[UserMessage],
        *,
        discard_removed: bool,
    ) -> list[UserMessage]:
        """Commit one normalized mutation and publish its live notifications."""
        inbox = self._state[target]

        truncated_start = math.trunc(start)
        offset = 0 if math.isnan(truncated_start) else truncated_start
        actual_start = max(len(inbox) + offset, 0) if offset < 0 else min(offset, len(inbox))

        truncated_delete_count = math.trunc(delete_count)
        actual_delete_count = min(
            max(
                0 if math.isnan(truncated_delete_count) else truncated_delete_count,
                0,
            ),
            len(inbox) - actual_start,
        )

        if actual_delete_count == 0 and len(inserted) == 0:
            return []

        outcome: str | None = "canceled" if discard_removed and actual_delete_count > 0 else None

        splice_data: dict[str, Any] = {
            "target": target,
            "start": actual_start,
        }
        if actual_delete_count > 0:
            splice_data["removed_count"] = actual_delete_count
        splice_data["inserted"] = tuple(inserted)
        if outcome is not None:
            splice_data["outcome"] = outcome

        self._validate(splice_data)

        event = self._session.append("agent/inbox/spliced", splice_data)

        # Apply the actual list mutation
        event_data = event.data if isinstance(event.data, dict) else splice_data
        event_inserted = event_data.get("inserted", ())
        removed = inbox[actual_start : actual_start + actual_delete_count]
        inbox[actual_start : actual_start + actual_delete_count] = list(event_inserted)

        if discard_removed:
            for message in removed:
                self._notifications.discarded(message)
        for message in event_inserted:
            self._notifications.inserted(message)

        return removed

    def _apply(self, splice: dict[str, Any]) -> list[UserMessage]:
        """Apply one normalized durable splice to the projection."""
        self._validate(splice)
        target = splice["target"]
        inbox = self._state[target]
        start = splice["start"]
        removed_count = splice.get("removed_count", 0)
        inserted = splice.get("inserted", ())
        removed = inbox[start : start + removed_count]
        inbox[start : start + removed_count] = list(inserted)
        return removed

    def _validate(self, splice: dict[str, Any]) -> None:
        """Validate one normalized splice against the current projection."""
        target = splice["target"]
        inbox = self._state[target]
        start = splice["start"]
        removed_count = splice.get("removed_count", 0)

        if (
            not isinstance(start, int)
            or start < 0
            or start > len(inbox)
            or not isinstance(removed_count, int)
            or removed_count < 0
            or start + removed_count > len(inbox)
        ):
            raise RuntimeError("invalid inbox splice")

        # Check for duplicate message identities
        candidate = (
            inbox[:start] + list(splice.get("inserted", ())) + inbox[start + removed_count :]
        )
        if target == "next-turn":
            all_messages = candidate + self.next_step
        else:
            all_messages = list(self.next_turn) + candidate

        ids: set[str] = set()
        for message in all_messages:
            mid = message.id
            if mid in ids:
                raise RuntimeError(f'message "{mid}" is already pending')
            ids.add(mid)
