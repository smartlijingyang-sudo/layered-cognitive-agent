"""Journal record serialization — dict ↔ JournalRecord conversion.

Extracted from ``lca.contracts.models.observability.journal`` to comply with
ADR-0015 (contracts layer has no behavior). This module owns the serialization
logic for the v2 journal envelope.
"""

from __future__ import annotations

from lca.contracts.models.observability.journal.journal import (
    Causation,
    DescriptorRef,
    JournalRecord,
    StampedEvent,
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
