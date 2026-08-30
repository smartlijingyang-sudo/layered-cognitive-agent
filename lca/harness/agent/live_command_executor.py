"""Recovery-aware execution seam for ordinary durable Session commands.

``SessionActivator`` exclusively owns materializing a live Session from durable
facts. This module owns the command-side sequence that repeatedly follows that
seam: recover one live owner, reject an unknown Session, invoke one operation,
and project its result into the stable command receipt. Keeping that sequence
behind one interface makes ordinary command routing shallow without absorbing
durable idempotency or approval decisions.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from lca.contracts.harness.collaboration.agent import LiveAgent, MessageReceipt
from lca.contracts.harness.act.command import CommandReceipt
from lca.harness.agent.activation import SessionActivator

LiveCommand = Callable[[LiveAgent], Awaitable[MessageReceipt | None]]
RejectCommand = Callable[[str, str, str], Awaitable[CommandReceipt]]


class LiveCommandExecutor:
    """Execute one ordinary Session command through the live-owner seam."""

    def __init__(self, *, activator: SessionActivator, reject: RejectCommand) -> None:
        self._activator = activator
        self._reject = reject

    async def execute(
        self,
        *,
        session_id: str,
        command_id: str,
        command: LiveCommand,
    ) -> CommandReceipt:
        """Recover a live owner, execute one command, and project its receipt.

        Commands that append a message return its committed sequence. Commands
        such as cancellation return ``None`` and are projected at the Session
        store's current sequence after their live-agent operation completes.
        """
        entry = await self._activator.entry_or_recover(session_id)
        if entry is None:
            return await self._reject(session_id, command_id, "unknown session")
        receipt = await command(entry.handle.agent)
        return CommandReceipt(
            command_id=command_id,
            session_id=session_id,
            seq=receipt.seq if receipt is not None else entry.store.current_seq,
            accepted=True,
        )


__all__ = ["LiveCommand", "LiveCommandExecutor"]
