"""Pick a frozen PlaneBindings from candidates + request. No I/O."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.plane import PlaneBindings, PlaneKind, PlaneRef
from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT, SANDBOX_OUTPUT_SUBDIR
from lca.contracts.protocols import Sandbox


class PlaneBindingError(ValueError):
    """Explicit plane requested but the candidate is missing or illegal."""


@dataclass(frozen=True)
class PlaneRequest:
    device_id: str = ""
    plane: str = ""
    extra_plane: str = ""


def ref_of(bindings: PlaneBindings, kind: PlaneKind) -> PlaneRef | None:
    if bindings.primary is not None and bindings.primary.kind is kind:
        return bindings.primary
    if bindings.secondary is not None and bindings.secondary.kind is kind:
        return bindings.secondary
    return None


def sandbox_ref_from(sandbox: Sandbox) -> PlaneRef:
    name = str(getattr(sandbox, "name", "") or "onlyboxes")
    root = SANDBOX_MOUNT_ROOT
    return PlaneRef(
        id=name,
        label="Onlyboxes",
        kind=PlaneKind.SANDBOX,
        root=root,
        outputs_dir=f"{root.rstrip('/')}/{SANDBOX_OUTPUT_SUBDIR}",
        platform="linux",
    )


def resolve_plane_bindings(
    machine: PlaneRef | None,
    sandbox: PlaneRef | None,
    request: PlaneRequest | None = None,
) -> PlaneBindings:
    """Exactly one primary. secondary only when extra_plane is explicit."""
    req = request if request is not None else PlaneRequest()
    wanted = _parse_kind(req.plane)
    extra = _parse_kind(req.extra_plane)

    primary = _select_primary(machine, sandbox, wanted)
    secondary = None
    if extra is not None:
        if primary is None:
            raise PlaneBindingError("extra_plane requires a primary plane")
        if extra is primary.kind:
            raise PlaneBindingError("extra_plane must differ from primary")
        secondary = _require(extra, machine, sandbox)
    return PlaneBindings(primary=primary, secondary=secondary)


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
