"""Prepared tool lifecycle catalog facts (ADR-0194 P1-10).

Cognition body prepares :class:`ToolJournalReceipt`; loop / act layer commits
via :class:`FactGateway` (``append_catalog_bound``). Side effects (cursor,
phase EP, diagnostics) remain at the caller until full migration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lca.contracts.harness.memory.events import (
    ToolCallResolvedCommitted,
    ToolDeniedCommitted,
    ToolInvokedCommitted,
    ToolStartedCommitted,
)
from lca.contracts.observability.evidence import EvidenceRef
from lca.contracts.protocols.loop.fact_gateway import SessionCatalogEvent


@dataclass(frozen=True, slots=True)
class ToolJournalReceipt:
    """One prepared tool lifecycle catalog fact ready for FactGateway commit."""

    catalog_event: SessionCatalogEvent
    actor: str = "body"


def _evidence_ref_wire(ref: EvidenceRef | None) -> dict[str, Any] | None:
    if ref is None:
        return None
    return ref.to_dict()


def tool_call_resolved_receipt(
    *,
    tool_name: str,
    tool_call_id: str,
    arguments: Mapping[str, Any],
    arguments_ref: EvidenceRef | None = None,
    actor: str = "brain",
) -> ToolJournalReceipt:
    """Build a ``tool.call.resolved.v1`` receipt for FactGateway commit."""
    return ToolJournalReceipt(
        catalog_event=ToolCallResolvedCommitted(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            arguments=dict(arguments),
            arguments_ref=_evidence_ref_wire(arguments_ref),
        ),
        actor=actor,
    )


def tool_denied_receipt(*, tool_name: str, reason: str, actor: str = "body") -> ToolJournalReceipt:
    """Build a ``tool.denied.v1`` receipt for FactGateway commit."""
    return ToolJournalReceipt(
        catalog_event=ToolDeniedCommitted(tool_name=tool_name, reason=reason),
        actor=actor,
    )


def tool_started_receipt(
    *,
    tool_name: str,
    invocation_id: str,
    arguments: Mapping[str, Any],
    arguments_ref: EvidenceRef | None = None,
    idempotency_key: str = "",
    actor: str = "body",
) -> ToolJournalReceipt:
    """Build a ``tool.started.v1`` receipt for FactGateway commit."""
    return ToolJournalReceipt(
        catalog_event=ToolStartedCommitted(
            tool_name=tool_name,
            invocation_id=invocation_id,
            arguments=dict(arguments),
            arguments_ref=_evidence_ref_wire(arguments_ref),
            idempotency_key=idempotency_key,
        ),
        actor=actor,
    )


def tool_invoked_receipt(
    *,
    tool_name: str,
    invocation_id: str,
    ok: bool,
    latency_ms: int,
    attempt: int,
    error: str = "",
    idempotency_key: str = "",
    files: tuple[dict[str, Any], ...] = (),
    arguments: Mapping[str, Any] | None = None,
    arguments_ref: EvidenceRef | None = None,
    output_ref: EvidenceRef | None = None,
    output_text: str | None = None,
    output_truncated: bool = False,
    projected_state: Mapping[str, Any] | None = None,
    actor: str = "body",
) -> ToolJournalReceipt:
    """Build a ``tool.invoked.v1`` receipt for FactGateway commit."""
    return ToolJournalReceipt(
        catalog_event=ToolInvokedCommitted(
            tool_name=tool_name,
            invocation_id=invocation_id,
            ok=ok,
            latency_ms=latency_ms,
            attempt=attempt,
            error=error,
            idempotency_key=idempotency_key,
            files=files,
            arguments=dict(arguments or {}),
            arguments_ref=_evidence_ref_wire(arguments_ref),
            output_ref=_evidence_ref_wire(output_ref),
            output_text=output_text,
            output_truncated=output_truncated,
            projected_state=dict(projected_state or {}),
        ),
        actor=actor,
    )


__all__ = [
    "ToolJournalReceipt",
    "tool_call_resolved_receipt",
    "tool_denied_receipt",
    "tool_invoked_receipt",
    "tool_started_receipt",
]
