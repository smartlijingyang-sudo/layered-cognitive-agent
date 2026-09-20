"""CapabilityGrant / EffectReceipt 领域模型契约测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant,
    EffectReceipt,
    LocalExecTarget,
    TargetKind,
)


def test_target_kind_values() -> None:
    assert set(TargetKind) == {
        TargetKind.SANDBOX,
        TargetKind.USER_MACHINE,
        TargetKind.POOL_WORKER,
    }


def test_capability_grant_frozen() -> None:
    grant = CapabilityGrant(
        job_id="j-1",
        idempotency_key="k-1",
        subject_user_id="u-1",
        subject_machine_id="m-1",
        operation="read_file",
        path_prefixes=["/home/alice/repo"],
        command_class=None,
        command_allowlist=[],
        expires_at=9999999999,
        approval_id=None,
        request_digest="sha256-abc",
    )
    with pytest.raises((TypeError, ValidationError)):
        grant.job_id = "mutate"  # type: ignore[misc]


def test_capability_grant_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        CapabilityGrant(
            job_id="j-1",
            idempotency_key="k-1",
            subject_user_id="u-1",
            subject_machine_id="m-1",
            operation="read_file",
            path_prefixes=[],
            command_class=None,
            command_allowlist=[],
            expires_at=9999999999,
            approval_id=None,
            request_digest="sha256-abc",
            unknown_field="bad",  # type: ignore[call-arg]
        )


def test_effect_receipt_frozen() -> None:
    receipt = EffectReceipt(
        job_id="j-1",
        idempotency_key="k-1",
        exit_code=0,
        success=True,
        error_kind=None,
        stdout_digest="sha256-x",
        stderr_digest=None,
    )
    with pytest.raises((TypeError, ValidationError)):
        receipt.success = False  # type: ignore[misc]


def test_local_exec_target_kinds() -> None:
    t = LocalExecTarget(
        kind=TargetKind.USER_MACHINE,
        id="m-win01",
        label="Alice-PC",
        capability_summary=["read_file", "write_file"],
    )
    assert t.kind == TargetKind.USER_MACHINE
