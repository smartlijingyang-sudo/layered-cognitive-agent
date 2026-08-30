"""Pick a frozen PlaneBindings from candidates + request. No I/O."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.plane import PlaneBindings, PlaneKind, PlaneRef
from lca.contracts.protocols import Sandbox
from lca.infrastructure.sandbox.paths import ONLYBOXES


class PlaneBindingError(ValueError):
    """Explicit plane requested but the candidate is missing or illegal."""


@dataclass(frozen=True)
class PlaneRequest:
    device_id: str = ""
    plane: str = ""
    extra_plane: str = ""
    execution_target: str = ""


def ref_of(bindings: PlaneBindings, kind: PlaneKind) -> PlaneRef | None:
    if bindings.primary is not None and bindings.primary.kind is kind:
        return bindings.primary
    if bindings.secondary is not None and bindings.secondary.kind is kind:
        return bindings.secondary
    return None


def make_sandbox_ref(*, name: str = "onlyboxes") -> PlaneRef:
    """The only writer of a sandbox PlaneRef. Disk identity is GuestLayout."""
    ident = name.strip() or "onlyboxes"
    return PlaneRef(
        id=ident,
        label="Onlyboxes",
        kind=PlaneKind.SANDBOX,
        root=ONLYBOXES.root,
        outputs_dir=ONLYBOXES.outputs_dir,
        platform="linux",
    )


def sandbox_ref_from(sandbox: Sandbox) -> PlaneRef:
    return make_sandbox_ref(name=str(getattr(sandbox, "name", "") or "onlyboxes"))


def resolve_plane_bindings(
    machine: PlaneRef | None,
    sandbox: PlaneRef | None,
    request: PlaneRequest | None = None,
) -> PlaneBindings:
    """Exactly one primary. secondary only when extra_plane is explicit.

    ``execution_target`` (sandbox|device|auto|none) is the LobeHub-aligned
    decision.  ``plane`` remains an explicit override when set.
    """
    req = request if request is not None else PlaneRequest()
    extra = _parse_kind(req.extra_plane)

    from lca.infrastructure.plane.execution_target import ExecutionTarget, parse_execution_target

    wanted = _parse_kind(req.plane)
    if wanted is None:
        requested = parse_execution_target(req.execution_target)
        if requested is ExecutionTarget.NONE:
            return PlaneBindings(primary=None)
        wanted = _kind_from_execution_target(req.execution_target, machine, sandbox)

    primary = _select_primary(machine, sandbox, wanted)
    secondary = None
    if extra is not None:
        if primary is None:
            raise PlaneBindingError("extra_plane requires a primary plane")
        if extra is primary.kind:
            raise PlaneBindingError("extra_plane must differ from primary")
        secondary = _require(extra, machine, sandbox)
    return PlaneBindings(primary=primary, secondary=secondary)


def _kind_from_execution_target(
    raw: str,
    machine: PlaneRef | None,
    sandbox: PlaneRef | None,
) -> PlaneKind | None:
    from lca.infrastructure.plane.execution_target import (
        ExecutionTarget,
        parse_execution_target,
        resolve_execution_target,
    )

    requested = parse_execution_target(raw)
    if requested is None:
        return None
    plan = resolve_execution_target(
        requested,
        device_online=machine is not None,
        sandbox_available=sandbox is not None,
        device_id=machine.id if machine is not None else None,
    )
    if plan.target is ExecutionTarget.DEVICE:
        return PlaneKind.MACHINE
    if plan.target is ExecutionTarget.SANDBOX:
        return PlaneKind.SANDBOX
    if plan.target is ExecutionTarget.NONE:
        return None
    return None


def _select_primary(
    machine: PlaneRef | None,
    sandbox: PlaneRef | None,
    wanted: PlaneKind | None,
) -> PlaneRef | None:
    if wanted is not None:
        return _require(wanted, machine, sandbox)
    if sandbox is not None and machine is None:
        return sandbox
    if machine is not None and sandbox is None:
        return machine
    if sandbox is not None and machine is not None:
        return sandbox
    return None


def _require(
    kind: PlaneKind,
    machine: PlaneRef | None,
    sandbox: PlaneRef | None,
) -> PlaneRef:
    found = machine if kind is PlaneKind.MACHINE else sandbox
    if found is None:
        raise PlaneBindingError(f"{kind.value} plane is not available")
    return found


def _parse_kind(raw: str) -> PlaneKind | None:
    text = (raw or "").strip().lower()
    if not text:
        return None
    try:
        return PlaneKind(text)
    except ValueError as exc:
        raise PlaneBindingError(f"unknown plane {raw!r}") from exc
