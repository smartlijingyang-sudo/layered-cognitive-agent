"""SSE → StampedEvent adapter for ``lca-ops logs``.

This module bridges the SSE transport layer and the domain rendering layer:
- Parses SSE blocks into JSON records
- Converts records into StampedEvent objects
- Feeds StampedEvents into ConsoleJournalProjector for rich terminal output

The key insight: ``lca-ops logs`` should not be a flat print loop. It should be
a stateful cognitive stream consumer that reuses ConsoleJournalProjector's
rich rendering (scenario cards, run cards, delegation visualization).
"""

from __future__ import annotations

import json
from typing import Any

from lca.contracts.models.observability.journal import StampedEvent
from lca.layer0_infra.observability.journal.journal_io import record_to_stamped

# SSE event types that don't map to StampedEvent (transport control signals).
_SSE_CONTROL_EVENTS = frozenset({"LiveGap"})


def parse_sse_block(block: str) -> dict[str, Any] | None:
    """Parse one SSE event block into a JSON record dict.

    Returns None for comments (lines starting with :) and empty blocks.
    """
    data = ""
    event_name = ""
    for line in block.splitlines():
        if line.startswith(":"):
            return None
        if line.startswith("event: "):
            event_name = line[7:].strip()
        elif line.startswith("data: "):
            data = line[6:]
    if not data:
        return None
    try:
        record = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None
    # Preserve SSE event name for control events.
    if event_name in _SSE_CONTROL_EVENTS:
        record["_sse_event"] = event_name
    return record


def sse_record_to_stamped(record: dict[str, Any]) -> StampedEvent | None:
    """Convert an SSE JSON record to a StampedEvent.

    Returns None for control events (LiveGap) or unknown event types.
    Control events are transport-level signals, not domain events.
    """
    # Control events don't map to StampedEvent.
    if record.get("_sse_event") in _SSE_CONTROL_EVENTS:
        return None
    try:
        return record_to_stamped(record)
    except Exception:
        # Malformed record — skip silently.
        return None


def extract_seq_from_record(record: dict[str, Any]) -> int:
    """Extract the sequence number from an SSE record for reconnection."""
    seq = record.get("seq")
    if isinstance(seq, int):
        return seq
    return 0
