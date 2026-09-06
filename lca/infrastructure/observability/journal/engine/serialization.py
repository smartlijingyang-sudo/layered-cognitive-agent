"""Journal record serialization — dict ↔ JournalRecord conversion.

Extracted from ``lca.contracts.models.observability.journal`` to comply with
ADR-0015 (contracts layer has no behavior). This module owns the serialization
logic for the v2 journal envelope.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from lca.contracts.atoms.ids.ids import RunId, TraceId
from lca.contracts.models.observability.journal.journal import (
    Causation,
    DescriptorRef,
    JournalRecord,
    RunScope,
    StampedEvent,
)


def _mapping_value(value: object, *, field_name: str) -> Mapping[str, object]:
    """Validate one JSON object before it enters the typed Journal envelope."""
    if not isinstance(value, Mapping):
        raise ValueError(f"JournalRecord.{field_name} must be an object")
    return {str(key): item for key, item in value.items()}


def _mapping_field(payload: Mapping[str, object], field_name: str) -> Mapping[str, object]:
    value = payload.get(field_name, {})
    if value is None:
        return {}
    return _mapping_value(value, field_name=field_name)


def _sequence_field(payload: Mapping[str, object], field_name: str) -> tuple[object, ...]:
    value = payload.get(field_name, ())
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"JournalRecord.{field_name} must be an array")
    return tuple(value)


def _string_field(payload: Mapping[str, object], field_name: str, *, default: str = "") -> str:
    value = payload.get(field_name, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"JournalRecord.{field_name} must be a string")
    return value


def _optional_string_field(payload: Mapping[str, object], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"JournalRecord.{field_name} must be a string or null")
    return value


def _int_field(payload: Mapping[str, object], field_name: str, *, default: int = 0) -> int:
    value = payload.get(field_name, default)
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"JournalRecord.{field_name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"JournalRecord.{field_name} must be an integer") from exc
    raise ValueError(f"JournalRecord.{field_name} must be an integer")


def _float_field(payload: Mapping[str, object], field_name: str, *, default: float = 0.0) -> float:
    value = payload.get(field_name, default)
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"JournalRecord.{field_name} must be a number")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"JournalRecord.{field_name} must be a number") from exc
    raise ValueError(f"JournalRecord.{field_name} must be a number")


def causation_to_dict(causation: Causation) -> dict[str, object]:
    """Serialize Causation to a plain dict."""
    return {
        "parent_event_id": causation.parent_event_id,
        "links": [dict(link) for link in causation.links],
    }


def causation_from_dict(payload: Mapping[str, object]) -> Causation:
    """Deserialize Causation from a plain dict."""
    links = tuple(
        {key: _string_field(link, key) for key in link}
        for item in _sequence_field(payload, "links")
        for link in (_mapping_value(item, field_name="causation.links[]"),)
    )
    return Causation(
        parent_event_id=_string_field(payload, "parent_event_id"),
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
        type=_string_field(payload, "type"),
        version=_int_field(payload, "version", default=1),
        payload_schema_version=_int_field(payload, "payload_schema_version", default=1),
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
    parent_run_id = _optional_string_field(payload, "parent_run_id")
    parent_trace_id = _optional_string_field(payload, "parent_trace_id")
    return RunScope(
        trace_id=TraceId(_string_field(payload, "trace_id")),
        run_id=RunId(_string_field(payload, "run_id")),
        parent_run_id=RunId(parent_run_id) if parent_run_id is not None else None,
        parent_trace_id=TraceId(parent_trace_id) if parent_trace_id is not None else None,
        delegation_id=_optional_string_field(payload, "delegation_id"),
        agent_role=_string_field(payload, "agent_role"),
        step=_int_field(payload, "step"),
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
    from lca.contracts.observability.evidence.evidence import EvidenceRef

    scope = scope_from_dict(_mapping_field(payload, "scope"))
    causation = causation_from_dict(_mapping_field(payload, "causation"))
    descriptor = descriptor_ref_from_dict(_mapping_field(payload, "descriptor"))
    evidence = tuple(
        EvidenceRef.from_dict(_mapping_value(item, field_name="evidence[]"))
        for item in _sequence_field(payload, "evidence")
    )
    return JournalRecord(
        schema="lca.journal/2",
        event_id=_string_field(payload, "event_id"),
        run_id=_string_field(payload, "run_id"),
        run_seq=_int_field(payload, "run_seq"),
        occurred_at=_float_field(payload, "occurred_at"),
        committed_at=_float_field(payload, "committed_at"),
        scope=scope,
        causation=causation,
        descriptor=descriptor,
        data=dict(_mapping_field(payload, "data")),
        evidence=evidence,
        plan_ref=_string_field(payload, "plan_ref"),
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
