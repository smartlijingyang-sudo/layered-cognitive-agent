"""Journal record serialization — dict ↔ JournalRecord conversion.

Extracted from ``lca.contracts.models.observability.journal`` to comply with
ADR-0015 (contracts layer has no behavior). This module owns the serialization
logic for the v2 journal envelope.
"""

from __future__ import annotations

from collections.abc import Mapping

from lca.contracts.models.observability.journal import (
    Causation,
    DescriptorRef,
    JournalRecord,
    RunScope,
    StampedEvent,
)


def causation_to_dict(causation: Causation) -> dict[str, object]:
    """Serialize Causation to a plain dict."""
    return {
        "parent_event_id": causation.parent_event_id,
        "links": [dict(link) for link in causation.links],
    }


def causation_from_dict(payload: Mapping[str, object]) -> Causation:
    """Deserialize Causation from a plain dict."""
    links_raw = payload.get("links", ()) or ()
    links: tuple[dict[str, str], ...] = tuple(
        dict(item) for item in links_raw if isinstance(item, Mapping)
    )
    return Causation(
        parent_event_id=str(payload.get("parent_event_id", "")),
        links=links,
    )


def descriptor_ref_to_dict(ref: DescriptorRef) -> dict[str, object]:
    """Serialize DescriptorRef to a plain dict."""
    return {
        "type": ref.type,
        "version": ref.version,
        "payload_schema_version": ref.payload_schema_version,
    }


def descriptor_ref_from_dict(payload: Mapping[str, object]) -> DescriptorRef:
    """Deserialize DescriptorRef from a plain dict."""
    return DescriptorRef(
        type=str(payload.get("type", "")),
        version=int(payload.get("version", 1)),
        payload_schema_version=int(payload.get("payload_schema_version", 1)),
    )


def scope_to_dict(scope: RunScope) -> dict[str, object]:
    """Serialize RunScope to a plain dict (handles brand-typed fields)."""
    return {
        "trace_id": str(scope.trace_id),
        "run_id": str(scope.run_id),
        "parent_run_id": str(scope.parent_run_id) if scope.parent_run_id else None,
        "parent_trace_id": str(scope.parent_trace_id) if scope.parent_trace_id else None,
        "delegation_id": scope.delegation_id,
        "agent_role": scope.agent_role,
        "step": scope.step,
    }


def scope_from_dict(payload: Mapping[str, object]) -> RunScope:
    """Deserialize RunScope from a plain dict (preserves brand-typed fields)."""

    def _opt_str(key: str) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        return str(value)

    return RunScope(
        trace_id=str(payload.get("trace_id", "")),
        run_id=str(payload.get("run_id", "")),
        parent_run_id=_opt_str("parent_run_id"),
        parent_trace_id=_opt_str("parent_trace_id"),
        delegation_id=_opt_str("delegation_id"),
        agent_role=str(payload.get("agent_role", "")),
        step=int(payload.get("step", 0)),
    )


def journal_record_to_dict(record: JournalRecord) -> dict[str, object]:
    """Serialize JournalRecord to a plain dict."""
    return {
        "schema": record.schema,
        "event_id": record.event_id,
        "run_id": record.run_id,
        "run_seq": record.run_seq,
        "occurred_at": record.occurred_at,
        "committed_at": record.committed_at,
        "scope": scope_to_dict(record.scope),
        "causation": causation_to_dict(record.causation),
        "descriptor": descriptor_ref_to_dict(record.descriptor),
        "data": dict(record.data),
        "evidence": [ref.to_dict() for ref in record.evidence],
        "plan_ref": record.plan_ref,
    }


def journal_record_from_dict(payload: Mapping[str, object]) -> JournalRecord:
    """Deserialize JournalRecord from a plain dict."""
    from lca.contracts.observability.evidence import EvidenceRef

    scope_raw = payload.get("scope", {}) or {}
    scope = scope_from_dict(scope_raw)
    causation = causation_from_dict(payload.get("causation", {}) or {})
    descriptor = descriptor_ref_from_dict(payload.get("descriptor", {}) or {})
    evidence_raw = payload.get("evidence", ()) or ()
    evidence = tuple(
        EvidenceRef.from_dict(item) for item in evidence_raw if isinstance(item, Mapping)
    )
    return JournalRecord(
        schema="lca.journal/2",
        event_id=str(payload.get("event_id", "")),
        run_id=str(payload.get("run_id", "")),
        run_seq=int(payload.get("run_seq", 0)),
        occurred_at=float(payload.get("occurred_at", 0.0)),
        committed_at=float(payload.get("committed_at", 0.0)),
        scope=scope,
        causation=causation,
        descriptor=descriptor,
        data=dict(payload.get("data", {}) or {}),
        evidence=evidence,
        plan_ref=str(payload.get("plan_ref", "")),
    )


def stamped_to_journal_record(
    stamped: StampedEvent,
    *,
    event_id: str,
    run_id: str,
    run_seq: int,
    occurred_at: float,
    committed_at: float,
    descriptor_version: int = 1,
    payload_schema_version: int = 1,
) -> JournalRecord:
    """Upgrade StampedEvent → JournalRecord (PR-3 migration bridge).

    No fields are lost; preview fields are preserved (removed in later PRs).
    Causation parent_event_id is looked up from seq→event_id map at append.
    """
    parent_event_id = ""
    return JournalRecord(
        schema="lca.journal/2",
        event_id=event_id,
        run_id=run_id,
        run_seq=run_seq,
        occurred_at=occurred_at,
        committed_at=committed_at,
        scope=stamped.scope,
        causation=Causation(parent_event_id=parent_event_id, links=()),
        descriptor=DescriptorRef(
            type=stamped.event_type,
            version=descriptor_version,
            payload_schema_version=payload_schema_version,
        ),
        data=stamped.data,
        evidence=(),
        plan_ref=stamped.plan_ref,
    )
