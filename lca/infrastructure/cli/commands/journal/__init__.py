"""Shared spine-event rendering helpers for the ``journal`` CLI family.

Production spine ledgers (``traces/runs/<id>/<run_id>.spine.jsonl``) carry
``event_id`` of the form ``<run_id>:<seq>`` plus an ISO ``ts`` field.
Legacy ``EventRecord``-shaped ledgers (written by ``FileSink`` in tests and
older backends) carry ``sequence`` and ``when`` instead. The journal viewers
must accept both shapes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def spine_event_seq(event: Mapping[str, Any]) -> int:
    """Derive a spine event's per-run sequence.

    Prefer ``event_id`` (``<run_id>:<seq>``); fall back to the legacy
    ``sequence`` field. Returns 0 when neither is parseable.
    """
    event_id = str(event.get("event_id") or "")
    if ":" in event_id:
        try:
            return int(event_id.rsplit(":", 1)[1])
        except ValueError:
            pass
    seq = event.get("sequence")
    if isinstance(seq, int):
        return seq
    if isinstance(seq, str) and seq.isdigit():
        return int(seq)
    return 0


def spine_event_when(event: Mapping[str, Any]) -> str:
    """Return the ISO timestamp of a spine event.

    Prefer ``ts`` (production ledger); fall back to ``when`` / ``when_corrected``
    (legacy ``EventRecord`` shape).
    """
    when = str(event.get("ts") or "")
    if when:
        return when
    return str(event.get("when") or event.get("when_corrected") or "")
