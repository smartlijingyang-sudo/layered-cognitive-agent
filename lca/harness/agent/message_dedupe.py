"""Durable inbox-message de-duplication helpers."""

from __future__ import annotations

from lca.contracts.harness.command import CommandReceipt
from lca.contracts.harness.session import SessionEvent


def existing_inbox_message_receipt(
    events: tuple[SessionEvent, ...],
    *,
    session_id: str,
    message_id: str,
    command_id: str,
) -> CommandReceipt | None:
    """Return the original append receipt when a stable inbox message already exists."""

    for event in events:
        if event.type != "inbox.spliced.v1" or event.data.get("op") != "append":
            continue
        raw_ids = event.data.get("message_ids")
        if isinstance(raw_ids, (list, tuple)) and message_id in raw_ids:
            return CommandReceipt(
                command_id=command_id,
                session_id=session_id,
                seq=event.seq,
                accepted=True,
            )
    return None


__all__ = ["existing_inbox_message_receipt"]
