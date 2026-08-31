"""Pure HTTP projections for the session gateway.

The session routes own transport orchestration; this module owns the stable
wire representation exposed by that transport. Keeping the projection pure
makes the HTTP seam easy to test without constructing a Starlette request or a
live session spine.
"""

from __future__ import annotations

import json
from typing import Any

from lca.contracts.harness.act.command import CommandReceipt
from lca.contracts.harness.state.projection import ProjectionChange, ProjectionSnapshot


def command_receipt_payload(receipt: CommandReceipt) -> dict[str, Any]:
    """Project a command receipt, including identity needed by clients."""
    return {
        "command_id": receipt.command_id,
        "session_id": receipt.session_id,
        "seq": receipt.seq,
        "accepted": receipt.accepted,
        "rejection_reason": receipt.rejection_reason,
    }


def accepted_receipt_payload(receipt: CommandReceipt) -> dict[str, Any]:
    """Project the compact response shared by control commands."""
    return {
        "accepted": receipt.accepted,
        "seq": receipt.seq,
        "session_id": receipt.session_id,
        "rejection_reason": receipt.rejection_reason,
    }


def snapshot_payload(session_id: str, snapshot: ProjectionSnapshot) -> dict[str, Any]:
    """Project the latest session snapshot."""
    return {
        "session_id": session_id,
        "as_of_seq": snapshot.as_of_seq,
        "values": snapshot.values,
    }


def sse_change_payload(change: ProjectionChange) -> str:
    """Serialize one projection change as a complete SSE event."""
    payload = {
        "session_id": change.session_id,
        "key": change.key,
        "version": change.version,
        "seq": change.seq,
        "value": change.value,
    }
    return f"id: {change.seq}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


__all__ = [
    "accepted_receipt_payload",
    "command_receipt_payload",
    "snapshot_payload",
    "sse_change_payload",
]
