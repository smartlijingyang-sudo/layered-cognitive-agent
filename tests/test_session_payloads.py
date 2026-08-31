from __future__ import annotations

from lca.contracts.harness.act.command import CommandReceipt
from lca.contracts.harness.state.projection import ProjectionChange, ProjectionSnapshot
from lca.plugins.transport.webserver.handlers.session_payloads import (
    accepted_receipt_payload,
    command_receipt_payload,
    snapshot_payload,
    sse_change_payload,
)


def test_command_receipt_projection_preserves_client_identity() -> None:
    receipt = CommandReceipt(
        command_id="cmd-1",
        session_id="session-1",
        seq=7,
        accepted=False,
        rejection_reason="duplicate",
    )

    assert command_receipt_payload(receipt) == {
        "command_id": "cmd-1",
        "session_id": "session-1",
        "seq": 7,
        "accepted": False,
        "rejection_reason": "duplicate",
    }


def test_control_receipt_projection_is_compact_but_complete() -> None:
    receipt = CommandReceipt("cmd-2", "session-2", 8, True)

    assert accepted_receipt_payload(receipt) == {
        "accepted": True,
        "seq": 8,
        "session_id": "session-2",
        "rejection_reason": None,
    }


def test_snapshot_projection_keeps_session_identity_and_values() -> None:
    snapshot = ProjectionSnapshot(as_of_seq=11, values={"status": "running"})

    assert snapshot_payload("session-3", snapshot) == {
        "session_id": "session-3",
        "as_of_seq": 11,
        "values": {"status": "running"},
    }


def test_sse_projection_emits_one_complete_event() -> None:
    change = ProjectionChange("session-4", "answer", 2, 12, {"text": "你好"})

    assert sse_change_payload(change) == (
        'id: 12\ndata: {"session_id": "session-4", "key": "answer", '
        '"version": 2, "seq": 12, "value": {"text": "你好"}}\n\n'
    )
