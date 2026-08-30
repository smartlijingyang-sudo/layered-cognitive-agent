"""schema-v2.0.0 provider —— ADR-0096 MVA-1.

把 ``JournalRecord`` 序列化为 ``EnvelopeV2`` (Pydantic v2 校验)。
字段名 ``data`` → ``payload``;``schema: lca.journal/2`` → ``schema_version: v2.0.0``。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.models.observability.journal import (
    Causation,
    DescriptorRef,
    JournalRecord,
    RunScope,
)
from lca.contracts.observability.schemas.v2 import SCHEMA_VERSION, EnvelopeV2


class EnvelopeV2Schema:
    """JournalSchema implementation for schema-v2.0.0."""

    version: str = SCHEMA_VERSION

    def serialize(self, record: JournalRecord) -> dict[str, Any]:
        raw: dict[str, Any] = {
            "schema_version": self.version,
            "event_id": record.event_id,
            "trace_id": str(record.scope.trace_id),
            "run_id": record.run_id,
            "run_seq": record.run_seq,
            "plan_ref": record.plan_ref,
            "occurred_at": record.occurred_at,
            "descriptor": {
                "type": record.descriptor.type,
                "version": record.descriptor.version,
                "payload_schema_version": record.descriptor.payload_schema_version,
            },
            "payload": dict(record.data),
            "scope": {
                "trace_id": str(record.scope.trace_id),
                "run_id": str(record.scope.run_id),
                "parent_run_id": (
                    str(record.scope.parent_run_id) if record.scope.parent_run_id else None
                ),
                "parent_trace_id": (
                    str(record.scope.parent_trace_id) if record.scope.parent_trace_id else None
                ),
                "delegation_id": record.scope.delegation_id,
                "agent_role": record.scope.agent_role,
                "step": record.scope.step,
            },
            "causation": (
                {
                    "parent_event_id": record.causation.parent_event_id,
                    "links": [dict(link) for link in record.causation.links],
                }
                if record.causation
                else {}
            ),
            "evidence": [ref.to_dict() for ref in record.evidence],
        }
        return EnvelopeV2.model_validate(raw).model_dump()

    def deserialize(self, data: dict[str, Any]) -> JournalRecord:
        from lca.contracts.observability.evidence import EvidenceRef
        from lca.contracts.observability.schemas.migrate import migrate_v1_to_v2

        normalized = migrate_v1_to_v2(data)
        env = EnvelopeV2.model_validate(normalized)
        scope_payload = env.scope or {}
        causation_payload = env.causation or {}
        descriptor_payload = env.descriptor or {}
        evidence: tuple[EvidenceRef, ...] = tuple(
            EvidenceRef.from_dict(item) for item in env.evidence if isinstance(item, dict)
        )
        parent_run_id = scope_payload.get("parent_run_id")
        parent_trace_id = scope_payload.get("parent_trace_id")
        links_raw = causation_payload.get("links", ()) or ()
        return JournalRecord(
            schema="lca.journal/2",
            event_id=env.event_id,
            run_id=env.run_id,
            run_seq=env.run_seq,
            occurred_at=env.occurred_at,
            committed_at=env.occurred_at,
            scope=RunScope(
                trace_id=TraceId(str(scope_payload.get("trace_id", env.trace_id))),
                run_id=RunId(str(scope_payload.get("run_id", env.run_id))),
                parent_run_id=RunId(str(parent_run_id)) if parent_run_id else None,
                parent_trace_id=TraceId(str(parent_trace_id)) if parent_trace_id else None,
                delegation_id=scope_payload.get("delegation_id"),
                agent_role=str(scope_payload.get("agent_role", "")),
                step=int(scope_payload.get("step", 0) or 0),
            ),
            causation=Causation(
                parent_event_id=str(causation_payload.get("parent_event_id", "")),
                links=tuple(dict(link) for link in links_raw if isinstance(link, dict)),
            ),
            descriptor=DescriptorRef(
                type=str(descriptor_payload.get("type", "")),
                version=int(descriptor_payload.get("version", 1) or 1),
                payload_schema_version=int(
                    descriptor_payload.get("payload_schema_version", 1) or 1
                ),
            ),
            data=dict(env.payload),
            evidence=evidence,
            plan_ref=env.plan_ref,
        )
