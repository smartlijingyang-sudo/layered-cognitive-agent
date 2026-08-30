"""Profile provider for durable approval-resume command idempotency."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.harness.session import SessionEvent
from lca.contracts.protocols.session.session_command_ledger import (
    ApprovalResumeDecision,
    ApprovalResumeDisposition,
    SessionCommandLedger,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Default event-sourced command-ledger configuration."""

    model_config = {"extra": "forbid"}


class EventSourcedSessionCommandLedger(SessionCommandLedger):
    """Derive approval command idempotency exclusively from Session facts.

    A matching ``approval.resolved.v1`` is not sufficient to replay a receipt:
    the command must also have a later durable ``session.checkpoint.v1``.  That
    distinction keeps a crash between approval acceptance and loop settlement
    fail-closed rather than reporting a successful replay prematurely.
    """

    def decide_approval_resume(
        self,
        events: tuple[SessionEvent, ...],
        *,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> ApprovalResumeDecision:
        """Return a pure command decision for one persisted approval."""

        resolution_seq: int | None = None
        checkpoint_seq: int | None = None
        for event in events:
            if event.type == "approval.resolved.v1":
                decision = self._resolution_decision(
                    event,
                    approval_id=approval_id,
                    payload=payload,
                    idempotency_key=idempotency_key,
                )
                if decision is not None:
                    if decision.disposition is ApprovalResumeDisposition.CONFLICT:
                        return decision
                    resolution_seq = event.seq
            elif (
                resolution_seq is not None
                and event.seq > resolution_seq
                and event.type == "session.checkpoint.v1"
            ):
                checkpoint_seq = event.seq

        if checkpoint_seq is not None:
            return ApprovalResumeDecision(
                disposition=ApprovalResumeDisposition.REPLAY,
                receipt_seq=checkpoint_seq,
            )
        if resolution_seq is not None:
            return ApprovalResumeDecision(
                disposition=ApprovalResumeDisposition.CONFLICT,
                reason="approval command was accepted but has no settled checkpoint",
            )
        return ApprovalResumeDecision(disposition=ApprovalResumeDisposition.PROCEED)

    @staticmethod
    def _resolution_decision(
        event: SessionEvent,
        *,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> ApprovalResumeDecision | None:
        """Validate one durable approval resolution against the incoming command."""

        resolved_approval = event.data.get("approval_id")
        command_id = event.data.get("command_id")
        resolved_payload = event.data.get("payload")
        if command_id == idempotency_key:
            if resolved_approval != approval_id or resolved_payload != payload:
                return ApprovalResumeDecision(
                    disposition=ApprovalResumeDisposition.CONFLICT,
                    reason="idempotency key is already bound to a different approval command",
                )
            return ApprovalResumeDecision(disposition=ApprovalResumeDisposition.PROCEED)
        if resolved_approval == approval_id:
            return ApprovalResumeDecision(
                disposition=ApprovalResumeDisposition.CONFLICT,
                reason="approval has already been resolved by a different command",
            )
        return None


@plugin(
    id="lca-session-command-ledger",
    requires=[],
    provides=["session_command_ledger"],
    implements=[SessionCommandLedger],
    layer="L3",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide event-sourced approval command idempotency so duplicate resume "
        "requests can be answered from durable Session facts after restart."
    ),
    test_suite="tests/harness/test_session_command_ledger.py",
)
async def setup(ctx: PluginContext, config: object) -> None:
    """Expose the default pure ledger to the booted Profile."""

    del config
    ctx.provide("session_command_ledger", EventSourcedSessionCommandLedger())


__all__ = ["Config", "EventSourcedSessionCommandLedger", "setup"]
