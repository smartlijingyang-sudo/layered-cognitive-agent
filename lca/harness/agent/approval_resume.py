"""Concurrent and durable approval-resume coordination for Session commands."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from lca.contracts.harness.command import CommandReceipt
from lca.contracts.protocols.session.session_command_ledger import (
    ApprovalResumeDisposition,
    SessionCommandLedger,
)
from lca.harness.agent.activation import SessionActivator

ReceiptCache = Callable[[str], CommandReceipt | None]
ReceiptRemember = Callable[[str, CommandReceipt], CommandReceipt]
RejectCommand = Callable[[str, str, str], Awaitable[CommandReceipt]]
LedgerProvider = Callable[[], SessionCommandLedger]


class ApprovalResumeCoordinator:
    """Serialize identical approval commands and consult durable facts before resume."""

    def __init__(
        self,
        *,
        activator: SessionActivator,
        ledger_provider: LedgerProvider,
        cached: ReceiptCache,
        remember: ReceiptRemember,
        reject: RejectCommand,
    ) -> None:
        self._activator = activator
        self._ledger_provider = ledger_provider
        self._cached = cached
        self._remember = remember
        self._reject = reject
        self._inflight: dict[tuple[str, str], tuple[str, str, asyncio.Future[CommandReceipt]]] = {}

    async def resume(
        self,
        *,
        session_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> CommandReceipt:
        """Resume once, replay durable receipts, and reject ambiguous duplicate commands."""

        cached = self._cached(idempotency_key)
        if cached is not None:
            return cached
        inflight_key = (session_id, idempotency_key)
        existing = self._inflight.get(inflight_key)
        if existing is not None:
            active_approval_id, active_payload, active_future = existing
            if active_approval_id != approval_id or active_payload != payload:
                return await self._reject(
                    session_id,
                    idempotency_key,
                    "idempotency key is already bound to a different approval command",
                )
            return await asyncio.shield(active_future)

        future: asyncio.Future[CommandReceipt] = asyncio.get_running_loop().create_future()
        self._inflight[inflight_key] = (approval_id, payload, future)
        try:
            receipt = await self._resume_once(
                session_id=session_id,
                approval_id=approval_id,
                payload=payload,
                idempotency_key=idempotency_key,
            )
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()
            raise
        else:
            future.set_result(receipt)
            return receipt
        finally:
            self._inflight.pop(inflight_key, None)

    async def _resume_once(
        self,
        *,
        session_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> CommandReceipt:
        store = self._activator.store_or_load(session_id)
        if store is None:
            return await self._reject(session_id, idempotency_key, "unknown session")
        decision = self._ledger_provider().decide_approval_resume(
            store.events(),
            approval_id=approval_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        if decision.disposition is ApprovalResumeDisposition.REPLAY:
            return self._remember(
                idempotency_key,
                CommandReceipt(
                    command_id=idempotency_key,
                    session_id=session_id,
                    seq=decision.receipt_seq or -1,
                    accepted=True,
                ),
            )
        if decision.disposition is ApprovalResumeDisposition.CONFLICT:
            return await self._reject(
                session_id,
                idempotency_key,
                decision.reason or "approval resume command conflicts with durable session facts",
            )

        entry = await self._activator.entry_or_recover(session_id)
        if entry is None:
            return await self._reject(session_id, idempotency_key, "unknown session")
        try:
            receipt_msg = await entry.handle.agent.resume_approval(
                approval_id,
                payload,
                idempotency_key=idempotency_key,
            )
        except ValueError as exc:
            return await self._reject(session_id, idempotency_key, str(exc))
        return self._remember(
            idempotency_key,
            CommandReceipt(
                command_id=idempotency_key,
                session_id=session_id,
                seq=receipt_msg.seq,
                accepted=True,
            ),
        )


__all__ = ["ApprovalResumeCoordinator"]
