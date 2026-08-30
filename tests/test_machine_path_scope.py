"""Machine path scope audit — pathScopeAudit parity."""

from __future__ import annotations

import pytest

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.contracts.models.core.result import ApprovalPendingError
from lca.infrastructure.runtime_plane.scope import (
    path_needs_approval,
    raise_if_out_of_scope,
    resolve_plane_path,
)


def _machine(root: str = "/home/lca-sandbox") -> PlaneRef:
    return PlaneRef(
        id="dev-1",
        label="box",
        kind=PlaneKind.MACHINE,
        root=root,
        outputs_dir=f"{root}/outputs",
        platform="linux",
    )


def test_relative_resolves_against_root() -> None:
    plane = _machine()
    assert resolve_plane_path("notes.txt", plane) == "/home/lca-sandbox/notes.txt"
    assert resolve_plane_path("./notes.txt", plane) == "/home/lca-sandbox/notes.txt"


def test_absolute_kept_as_is() -> None:
    plane = _machine()
    scratch = "/tmp/scratch.txt"  # noqa: S108
    assert resolve_plane_path(scratch, plane) == scratch


def test_temp_does_not_need_approval() -> None:
    plane = _machine()
    scratch = "/tmp/scratch.txt"  # noqa: S108
    assert not path_needs_approval(scratch, plane)


def test_outside_root_needs_approval() -> None:
    plane = _machine()
    assert path_needs_approval("/etc/passwd", plane)


def test_raise_if_out_of_scope_blocks_escape() -> None:
    plane = _machine()
    with pytest.raises(ApprovalPendingError):
        raise_if_out_of_scope("/etc/passwd", plane)


def test_sandbox_skips_approval() -> None:
    sandbox = PlaneRef(
        id="sb-1",
        label="Onlyboxes",
        kind=PlaneKind.SANDBOX,
        root="/mnt/data",
        outputs_dir="/mnt/data/outputs",
    )
    assert not path_needs_approval("/anywhere/outside", sandbox)
