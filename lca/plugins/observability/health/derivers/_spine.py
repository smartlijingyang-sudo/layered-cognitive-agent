"""Shared spine-event utilities for the eight PR-1 derivers (Task 1.3).

Per spec §10.5 (evidence property 3) every condition MUST carry at least
one ``EvidenceRef``. The fold function does not re-validate this — the
obligation lives with each deriver because the evidence is deriver-local.
This module centralises the spine-event parsing so each deriver stays
small and the parsing rules live in one place.

Each spine event is a plain ``dict`` shaped like a line in
``<run_id>.spine.jsonl``. Required keys (per the fold layer's contract):

    event_id         str — ``"run_<id>:<seq>"``; split on ``:`` for seq.
    ts               str — ISO-8601 timestamp.
    run_id           str — duplicated from event_id; folded passes it through.
    execution_point  str — one of SPINE_EXECUTION_POINTS.
    payload          dict — EP-specific shape; see deriver docstrings.

Derivers MUST NOT assume event ordering beyond what the EP vocabulary
implies (the fold pre-sorts). Grouping by ``invocation_id`` is the only
cross-event correlation a deriver is allowed to do.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from lca.contracts.observability.health.evidence_ref import EvidenceRef


class SpineEvent(TypedDict):
    """One spine event as the fold passes it to the derivers.

    ``payload`` is intentionally untyped — the EP vocabulary owns the
    shape; derivers consume the fields they need and ignore the rest.
    """

    event_id: str
    ts: str
    run_id: str
    execution_point: str
    payload: dict  # type: ignore[type-arg]


def parse_run_id(event_id: str) -> str:
    """Extract ``run_id`` from a spine ``event_id`` of the form ``run_<id>:<seq>``.

    Examples:
        >>> parse_run_id("run_3383288d63e7:18")
        'run_3383288d63e7'
        >>> parse_run_id("run_3cf6e7c036b3:386")
        'run_3cf6e7c036b3'
    """
    head, _sep, _seq = event_id.partition(":")
    # ``run_<id>`` — strip the trailing ``_<seq>`` we already separated off;
    # but the head itself contains an underscore before the id, so we keep
    # the whole head as the run_id (matches what the producer writes).
    return head


def parse_seq(event_id: str) -> int:
    """Extract the 1-based monotonic ``seq`` from a spine ``event_id``.

    Examples:
        >>> parse_seq("run_3383288d63e7:18")
        18
        >>> parse_seq("run_3cf6e7c036b3:386")
        386
    """
    _head, _sep, seq_str = event_id.partition(":")
    return int(seq_str)


def parse_observed_at(ts: str) -> float:
    """Parse an ISO-8601 timestamp into epoch_seconds (float).

    The fold uses this to stamp ``observed_at`` on every condition so
    reports can be ordered by time-of-observation per ``type``.
    """
    # Python's fromisoformat handles ``+00:00`` since 3.11; before that,
    # ``Z`` had to be substituted. The fold layer guarantees the producer
    # emits ``+00:00`` so no substitution is needed here.
    return datetime.fromisoformat(ts).timestamp()


def make_evidence_ref(event: SpineEvent) -> EvidenceRef:
    """Build a frozen ``EvidenceRef`` from a single spine event.

    ``spine_path`` is empty here — the fold fills it in after the fact
    because the fold owns the absolute path, not the deriver. Derivers
    pass back the *index* of the event in the spine sequence; the fold
    resolves that to a path during report assembly.

    ``run_id`` is read from ``event["run_id"]`` if present (the fold
    injects it for the derivers), or extracted from the ``event_id``
    prefix as a fallback. The audit runs on disk do not carry a
    top-level ``run_id`` — they only have it in the payload — so the
    fallback keeps the derivers runnable against raw JSONL without
    requiring a pre-processor.
    """
    run_id = event.get("run_id") or parse_run_id(event["event_id"])
    return EvidenceRef(
        run_id=run_id,
        spine_path="",  # resolved by fold layer post-evaluate
        event_id=event["event_id"],
        execution_point=event["execution_point"],
        seq=parse_seq(event["event_id"]),
    )


def filter_by_ep(events: list[SpineEvent], ep: str) -> list[SpineEvent]:
    """Return events whose ``execution_point`` exactly matches ``ep``.

    Order preserved. Returns an empty list when no events match.
    """
    return [e for e in events if e["execution_point"] == ep]


def group_by_invocation(events: list[SpineEvent], ep: str) -> dict[str, list[SpineEvent]]:
    """Group events whose ``execution_point == ep`` by their ``invocation_id``.

    Events without a payload-level ``invocation_id`` are dropped — they
    cannot be matched to a tool call. The fold does not re-validate
    this; derivers that need grouping must call this helper rather than
    re-implementing the logic.
    """
    out: dict[str, list[SpineEvent]] = {}
    for e in events:
        if e["execution_point"] != ep:
            continue
        inv_id = e["payload"].get("invocation_id")
        if not isinstance(inv_id, str) or not inv_id:
            continue
        out.setdefault(inv_id, []).append(e)
    return out


__all__ = [
    "EvidenceRef",
    "SpineEvent",
    "filter_by_ep",
    "group_by_invocation",
    "make_evidence_ref",
    "parse_observed_at",
    "parse_run_id",
    "parse_seq",
]
