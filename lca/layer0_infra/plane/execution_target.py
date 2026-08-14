"""executionTarget resolution — sandbox | device | auto | none + fallback.

Aligns with LobeHub ``resolveExecutionTarget()``.  Pure decision: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExecutionTarget(str, Enum):
    SANDBOX = "sandbox"
    DEVICE = "device"
    AUTO = "auto"
    NONE = "none"


@dataclass(frozen=True)
class ExecutionPlan:
    target: ExecutionTarget
    device_id: str | None = None
    fallback: ExecutionTarget | None = None


def parse_execution_target(raw: str) -> ExecutionTarget | None:
    text = (raw or "").strip().lower()
    if not text:
        return None
    if text in {"local", "machine"}:
        return ExecutionTarget.DEVICE
    try:
        return ExecutionTarget(text)
    except ValueError:
        return None


def resolve_execution_target(
    requested: ExecutionTarget,
    *,
    device_online: bool,
    sandbox_available: bool,
    device_id: str | None = None,
) -> ExecutionPlan:
    """Pick a concrete target.  Missing environments fall back; never silently invent one."""
    if requested is ExecutionTarget.NONE:
        return ExecutionPlan(target=ExecutionTarget.NONE)

    if requested is ExecutionTarget.SANDBOX:
        if sandbox_available:
            return ExecutionPlan(target=ExecutionTarget.SANDBOX)
        if device_online:
            return ExecutionPlan(
                target=ExecutionTarget.DEVICE,
                device_id=device_id,
                fallback=ExecutionTarget.DEVICE,
            )
        return ExecutionPlan(target=ExecutionTarget.NONE)

    if requested is ExecutionTarget.DEVICE:
        if device_online:
            return ExecutionPlan(target=ExecutionTarget.DEVICE, device_id=device_id)
        if sandbox_available:
            return ExecutionPlan(
                target=ExecutionTarget.SANDBOX,
                fallback=ExecutionTarget.SANDBOX,
            )
        return ExecutionPlan(target=ExecutionTarget.NONE)

    # AUTO: prefer the user's machine, then sandbox
    if device_online:
        return ExecutionPlan(target=ExecutionTarget.DEVICE, device_id=device_id)
    if sandbox_available:
        return ExecutionPlan(target=ExecutionTarget.SANDBOX)
    return ExecutionPlan(target=ExecutionTarget.NONE)
