"""executionTarget fallback matrix — LobeHub resolveExecutionTarget parity."""

from __future__ import annotations

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.execution_target import (
    ExecutionTarget,
    parse_execution_target,
    resolve_execution_target,
)
from lca.infrastructure.runtime_plane.resolve import PlaneRequest, resolve_plane_bindings


def _machine() -> PlaneRef:
    return PlaneRef(
        id="dev-1",
        label="box",
        kind=PlaneKind.MACHINE,
        root="/tmp/root",  # noqa: S108
        outputs_dir="/tmp/root/outputs",  # noqa: S108
    )


def _sandbox() -> PlaneRef:
    return PlaneRef(
        id="onlyboxes",
        label="Onlyboxes",
        kind=PlaneKind.SANDBOX,
        root="/mnt/data",
        outputs_dir="/mnt/data/outputs",
        platform="linux",
    )


def test_parse_aliases() -> None:
    assert parse_execution_target("local") is ExecutionTarget.DEVICE
    assert parse_execution_target("machine") is ExecutionTarget.DEVICE
    assert parse_execution_target("auto") is ExecutionTarget.AUTO
    assert parse_execution_target("") is None


def test_sandbox_falls_back_to_device() -> None:
    plan = resolve_execution_target(
        ExecutionTarget.SANDBOX,
        device_online=True,
        sandbox_available=False,
        device_id="dev-1",
    )
    assert plan.target is ExecutionTarget.DEVICE
    assert plan.fallback is ExecutionTarget.DEVICE


def test_device_falls_back_to_sandbox() -> None:
    plan = resolve_execution_target(
        ExecutionTarget.DEVICE,
        device_online=False,
        sandbox_available=True,
    )
    assert plan.target is ExecutionTarget.SANDBOX
    assert plan.fallback is ExecutionTarget.SANDBOX


def test_auto_prefers_device() -> None:
    plan = resolve_execution_target(
        ExecutionTarget.AUTO,
        device_online=True,
        sandbox_available=True,
        device_id="dev-1",
    )
    assert plan.target is ExecutionTarget.DEVICE


def test_none_is_none() -> None:
    plan = resolve_execution_target(
        ExecutionTarget.NONE,
        device_online=True,
        sandbox_available=True,
    )
    assert plan.target is ExecutionTarget.NONE


def test_bindings_honor_execution_target_none() -> None:
    bindings = resolve_plane_bindings(
        _machine(),
        _sandbox(),
        PlaneRequest(execution_target="none"),
    )
    assert bindings.primary is None


def test_bindings_auto_picks_machine() -> None:
    bindings = resolve_plane_bindings(
        _machine(),
        _sandbox(),
        PlaneRequest(execution_target="auto"),
    )
    assert bindings.primary is not None
    assert bindings.primary.kind is PlaneKind.MACHINE


def test_bindings_sandbox_when_no_device() -> None:
    bindings = resolve_plane_bindings(
        None,
        _sandbox(),
        PlaneRequest(execution_target="device"),
    )
    assert bindings.primary is not None
    assert bindings.primary.kind is PlaneKind.SANDBOX
