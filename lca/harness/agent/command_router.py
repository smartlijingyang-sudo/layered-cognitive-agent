"""Typed command router for the durable Session Spine."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.collaboration.agent import ContextMessage, UserMessage
from lca.contracts.harness.act.command import CommandReceipt
from lca.contracts.harness.memory.events import CommandRejected
from lca.contracts.protocols.session.session_command_ledger import SessionCommandLedger
from lca.harness.agent.activation import SessionActivator
from lca.harness.agent.approval_resume import ApprovalResumeCoordinator
from lca.harness.agent.live_command_executor import LiveCommandExecutor
from lca.harness.agent.message_dedupe import existing_inbox_message_receipt


class AgentCommandRouter:
    """Translate typed session commands into calls on an activated live agent.

    The router owns public command admission and the ordinary in-process receipt
    cache. Durable approval coordination and durable inbox-message de-duplication
    are separate helpers so command concerns do not become another runtime loop.
    """

    def __init__(
        self,
        activator: SessionActivator,
        *,
        command_ledger_provider: Callable[[], SessionCommandLedger],
    ) -> None:
        self._activator = activator
        self._idempotency: dict[str, CommandReceipt] = {}
        self._approval = ApprovalResumeCoordinator(
            activator=activator,
            ledger_provider=command_ledger_provider,
            cached=self._cached,
            remember=self._remember,
            reject=self._reject,
        )
        self._live_commands = LiveCommandExecutor(activator=activator, reject=self._reject)

    async def create_session(
        self,
        *,
        idempotency_key: str,
        profile: str,
        preset: str | None,
        options: dict[str, Any] | None,
        session_id: str | None = None,
    ) -> CommandReceipt:
        """Create a session once for one idempotency key."""

        cached = self._cached(idempotency_key)
        if cached is not None:
            return cached
        handle = await self._activator.create(
            profile,
            preset,
            session_id=session_id,
            options=options,
        )
        entry = self._activator.entry_for(handle.agent.session_id)
        if entry is None:
            raise RuntimeError("created session has no active owner")
        return self._remember(
            idempotency_key,
            CommandReceipt(
                command_id=idempotency_key,
                session_id=handle.agent.session_id,
                seq=entry.store.current_seq,
                accepted=True,
            ),
        )

    async def dispatch_message(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        content: str,
        role: str,
        message_id: str | None = None,
    ) -> CommandReceipt:
        """Append an idempotent user message through a durable session owner.

        A stable message ID permits recovery after a worker or gateway restart:
        before live invocation, the router folds prior inbox append facts and
        reuses the original receipt instead of appending a second message.
        """

        cached = self._cached(idempotency_key)
        if cached is not None:
            return cached
        entry = await self._activator.entry_or_recover(session_id)
        if entry is None:
            return await self._reject(session_id, idempotency_key, "unknown session")
        durable_message_id = message_id.strip() if isinstance(message_id, str) else ""
        if durable_message_id:
            accepted = existing_inbox_message_receipt(
                entry.store.events(),
                session_id=session_id,
                message_id=durable_message_id,
                command_id=idempotency_key,
            )
            if accepted is not None:
                return self._remember(idempotency_key, accepted)
        receipt_msg = await entry.handle.agent.followup(
            UserMessage(content=content, role=role, message_id=durable_message_id)
        )
        return self._remember(
            idempotency_key,
            CommandReceipt(
                command_id=idempotency_key,
                session_id=session_id,
                seq=receipt_msg.seq,
                accepted=True,
            ),
        )

    async def cancel(self, *, session_id: str, keep_inbox: bool) -> CommandReceipt:
        """Cancel an active or recoverable session without treating it as idempotent."""

        command_id = new_id("cmd")
        return await self._live_commands.execute(
            session_id=session_id,
            command_id=command_id,
            command=lambda agent: agent.cancel(keep_inbox=keep_inbox),
        )

    async def resume_approval(
        self,
        *,
        session_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> CommandReceipt:
        """Resolve an approval through the profile-selected durable ledger."""

        return await self._approval.resume(
            session_id=session_id,
            approval_id=approval_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    async def steer(self, *, session_id: str, content: str) -> CommandReceipt:
        """Send a non-idempotent steering message to a recoverable session."""

        command_id = new_id("cmd")
        return await self._live_commands.execute(
            session_id=session_id,
            command_id=command_id,
            command=lambda agent: agent.steer(UserMessage(content=content)),
        )

    async def inject(self, *, session_id: str, source: str, content: str) -> CommandReceipt:
        """Inject non-user context into a recoverable session."""

        command_id = new_id("cmd")
        return await self._live_commands.execute(
            session_id=session_id,
            command_id=command_id,
            command=lambda agent: agent.inject(ContextMessage(content=content, source=source)),
        )

    def _cached(self, idempotency_key: str) -> CommandReceipt | None:
        return self._idempotency.get(idempotency_key)

    def _remember(self, idempotency_key: str, receipt: CommandReceipt) -> CommandReceipt:
        self._idempotency[idempotency_key] = receipt
        return receipt

    async def _reject(self, session_id: str, command_id: str, reason: str) -> CommandReceipt:
        entry = self._activator.entry_for(session_id)
        seq = -1
        if entry is not None:
            event = await entry.store.append(CommandRejected(command_type="unknown", reason=reason))
            seq = event.seq
        return CommandReceipt(
            command_id=command_id,
            session_id=session_id,
            seq=seq,
            accepted=False,
            rejection_reason=reason,
        )


__all__ = ["AgentCommandRouter"]
