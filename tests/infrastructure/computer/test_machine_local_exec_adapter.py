"""MachineLocalExecAdapter 满足 LocalExecPort，错误形状与 FakeCompanionProvider 一致。"""

from __future__ import annotations

import pathlib
import tempfile
import time
from typing import Any

import pytest

from lca.contracts.models.core.execution.local_exec import CapabilityGrant, TargetKind
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.contracts.protocols.runtime.infra.infra import LocalExecPort
from lca.infrastructure.computer.machine.adapter import MachineLocalExecAdapter
from lca.infrastructure.computer.machine.machine import MachineComputer
from lca.infrastructure.file.store import LocalFileStore


class _FakeTransport:
    async def computer_op(
        self, op: str, args: dict[str, Any], *, timeout_s: int = 60
    ) -> dict[str, Any]:
        return {"success": True, "content": "ok"}

    async def write_files(self, files: Any, **kwargs: Any) -> Any:
        return None


def _make_adapter() -> MachineLocalExecAdapter:
    plane = PlaneRef(
        id="m-1",
        label="test-machine",
        kind=PlaneKind.MACHINE,
        root="/repo",
        outputs_dir="/repo/out",
    )
    store = LocalFileStore(pathlib.Path(tempfile.mkdtemp()))
    mc = MachineComputer(plane=plane, transport=_FakeTransport(), store=store)
    return MachineLocalExecAdapter(computer=mc, machine_id="m-1", label="test-machine")


def test_adapter_satisfies_protocol() -> None:
    assert isinstance(_make_adapter(), LocalExecPort)


def test_target_kind_is_user_machine() -> None:
    assert _make_adapter().target.kind == TargetKind.USER_MACHINE


@pytest.mark.asyncio
async def test_grant_expired_error_kind() -> None:
    grant = CapabilityGrant(
        job_id="j-1",
        idempotency_key="k-1",
        subject_user_id="u-1",
        subject_machine_id="m-1",
        operation="read_file",
        path_prefixes=["/repo"],
        command_class=None,
        command_allowlist=[],
        expires_at=int(time.time()) - 1,
        approval_id=None,
        request_digest="d-1",
    )
    receipt = await _make_adapter().execute("read_file", {"path": "/repo/a.py"}, grant)
    assert receipt.success is False
    assert receipt.error_kind == "grant_expired"


@pytest.mark.asyncio
async def test_scope_violation_error_kind() -> None:
    grant = CapabilityGrant(
        job_id="j-2",
        idempotency_key="k-2",
        subject_user_id="u-1",
        subject_machine_id="m-1",
        operation="read_file",
        path_prefixes=["/repo"],
        command_class=None,
        command_allowlist=[],
        expires_at=int(time.time()) + 3600,
        approval_id=None,
        request_digest="d-2",
    )
    receipt = await _make_adapter().execute("read_file", {"path": "/etc/passwd"}, grant)
    assert receipt.success is False
    assert receipt.error_kind == "scope_violation"


@pytest.mark.asyncio
async def test_happy_path_execution() -> None:
    grant = CapabilityGrant(
        job_id="j-3",
        idempotency_key="k-3",
        subject_user_id="u-1",
        subject_machine_id="m-1",
        operation="read_file",
        path_prefixes=["/repo"],
        command_class=None,
        command_allowlist=[],
        expires_at=int(time.time()) + 3600,
        approval_id=None,
        request_digest="d-3",
    )
    receipt = await _make_adapter().execute("read_file", {"path": "/repo/a.py"}, grant)
    assert receipt.success is True
    assert receipt.error_kind is None
    assert receipt.stdout_digest is not None
