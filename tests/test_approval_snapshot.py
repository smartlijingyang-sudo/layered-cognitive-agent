from __future__ import annotations

import pytest

from lca.harness.declarative.approval import ApprovalRequestSnapshot


def test_approval_snapshot_expires_at_boundary() -> None:
    snapshot = ApprovalRequestSnapshot(
        approval_id="approval-1",
        task_id="task-1",
        expires_at=100.0,
        requested_scopes=("crm.write",),
    )

    assert snapshot.is_expired(99.9) is False
    assert snapshot.is_expired(100.0) is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"approval_id": "", "task_id": "task", "expires_at": 100.0},
        {"approval_id": "approval", "task_id": "", "expires_at": 100.0},
        {"approval_id": "approval", "task_id": "task", "expires_at": 0.0},
    ],
)
def test_approval_snapshot_rejects_invalid_metadata(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ApprovalRequestSnapshot(**kwargs)


def test_approval_snapshot_ensure_active_rejects_expired_request() -> None:
    snapshot = ApprovalRequestSnapshot(
        approval_id="approval-1",
        task_id="task-1",
        expires_at=100.0,
    )

    with pytest.raises(ValueError, match="expired"):
        snapshot.ensure_active(100.0)
