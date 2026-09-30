"""Expand one memory claim into the eight fields a person can audit.

The host maps its store into ``ExplainableRecord``. This module does not
know the store. ``supersession_chain`` lists the claim and then each older
revision it replaced, and stops when the link leaves the supplied records.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExplainableRecord:
    """One stored claim, active or already superseded."""

    record_id: str
    body: str
    kind: str
    importance: float = 0.5
    confidence: float | None = None
    source: str = ""
    trigger: str = ""
    recorded_on: str = ""
    quote: str = ""
    revision_of: str | None = None


@dataclass(frozen=True, slots=True)
class ClaimExplanation:
    """The eight audit fields for one claim."""

    claim: str
    kind: str
    salience: float
    attribution: str
    quote: str
    timeline: str
    confidence: float | None
    supersession_chain: tuple[str, ...]


def explain_record(
    target: ExplainableRecord,
    records: Sequence[ExplainableRecord],
) -> ClaimExplanation:
    """Explain ``target`` using ``records`` for its revision links."""

    by_id = {record.record_id: record for record in records}
    chain = [target.record_id]
    seen = {target.record_id}
    cursor = target.revision_of
    while cursor and cursor not in seen and cursor in by_id:
        seen.add(cursor)
        chain.append(cursor)
        cursor = by_id[cursor].revision_of
    recorded = target.recorded_on.strip()
    trigger = target.trigger.strip()
    if recorded and trigger:
        timeline = f"{recorded}，{trigger}"
    else:
        timeline = recorded or trigger or "unspecified"
    return ClaimExplanation(
        claim=target.body.strip(),
        kind=target.kind,
        salience=target.importance,
        attribution=target.source.strip() or "unspecified",
        quote=target.quote.strip(),
        timeline=timeline,
        confidence=target.confidence,
        supersession_chain=tuple(chain),
    )


__all__ = ["ClaimExplanation", "ExplainableRecord", "explain_record"]
