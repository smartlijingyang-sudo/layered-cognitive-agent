"""Machine path scope audit — pathScopeAudit parity."""

from __future__ import annotations

import pytest

from lca.contracts.models.core.execution.result import ApprovalPendingError
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.scope.scope import (
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


def _windows_machine(root: str = "F:\\work") -> PlaneRef:
    return PlaneRef(
        id="m-lipcmain",
        label="lipcmain",
        kind=PlaneKind.MACHINE,
        root=root,
        outputs_dir=f"{root}\\outputs",
        platform="Windows",
        home="C:\\Users\\li",
    )


def test_windows_resolve_collapses_parent_segments() -> None:
    plane = _windows_machine()
    assert resolve_plane_path("F:\\work\\..\\secret.txt", plane) == "F:\\secret.txt"
    assert resolve_plane_path("F:\\work\\notes.md", plane) == "F:\\work\\notes.md"


def test_windows_parent_escape_needs_approval() -> None:
    plane = _windows_machine()
    assert path_needs_approval("F:\\work\\..\\secret.txt", plane)
    assert path_needs_approval("F:\\work\\a\\..\\..\\secret.txt", plane)
    assert not path_needs_approval("F:\\work\\notes.md", plane)


def test_windows_outside_root_needs_approval() -> None:
    plane = _windows_machine()
    target = "C:\\Users\\li\\AppData\\Roaming\\clash-verge\\verge.yaml"
    assert path_needs_approval(target, plane)
    with pytest.raises(ApprovalPendingError):
        raise_if_out_of_scope(target, plane)


def test_windows_temp_does_not_need_approval() -> None:
    plane = _windows_machine()
    assert not path_needs_approval("C:\\Users\\li\\AppData\\Local\\Temp\\x.txt", plane)
