"""Machine path scope — path resolution and access policy verdicts."""

from __future__ import annotations

from lca.contracts.models.core.execution.local_exec import AccessScope, AccessVerdict
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.access.grant import default_access_scope
from lca.infrastructure.runtime_plane.access.policy import decide_access
from lca.infrastructure.runtime_plane.paths.paths import resolve_plane_path


def _machine(root: str = "/home/lca-sandbox") -> PlaneRef:
    return PlaneRef(
        id="dev-1",
        label="box",
        kind=PlaneKind.MACHINE,
        root=root,
        outputs_dir=f"{root}/outputs",
        platform="linux",
    )


def _verdict(operation: str, plane: PlaneRef, paths: list[str]) -> AccessVerdict:
    return decide_access(
        operation,
        scope=default_access_scope(plane, operation),
        plane=plane,
        paths=paths,
    ).verdict


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
    assert _verdict("read_file", plane, [scratch]) is AccessVerdict.ALLOW


def test_outside_root_needs_approval() -> None:
    plane = _machine()
    assert _verdict("read_file", plane, ["/etc/passwd"]) is AccessVerdict.NEEDS_APPROVAL


def test_sandbox_skips_approval() -> None:
    sandbox = PlaneRef(
        id="sb-1",
        label="Onlyboxes",
        kind=PlaneKind.SANDBOX,
        root="/mnt/data",
        outputs_dir="/mnt/data/outputs",
    )
    scope = AccessScope()
    decision = decide_access(
        "read_file",
        scope=scope,
        plane=sandbox,
        paths=["/anywhere/outside"],
    )
    assert decision.verdict is AccessVerdict.ALLOW


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
    assert (
        _verdict("read_file", plane, ["F:\\work\\..\\secret.txt"]) is AccessVerdict.NEEDS_APPROVAL
    )
    assert (
        _verdict("read_file", plane, ["F:\\work\\a\\..\\..\\secret.txt"])
        is AccessVerdict.NEEDS_APPROVAL
    )
    assert _verdict("read_file", plane, ["F:\\work\\notes.md"]) is AccessVerdict.ALLOW


def test_windows_outside_root_needs_approval() -> None:
    plane = _windows_machine()
    target = "C:\\Users\\li\\AppData\\Roaming\\clash-verge\\verge.yaml"
    assert _verdict("read_file", plane, [target]) is AccessVerdict.ALLOW
    outside = "D:\\other\\secret.txt"
    assert _verdict("read_file", plane, [outside]) is AccessVerdict.NEEDS_APPROVAL


def test_windows_temp_does_not_need_approval() -> None:
    plane = _windows_machine()
    temp = "C:\\Users\\li\\AppData\\Local\\Temp\\x.txt"
    assert _verdict("read_file", plane, [temp]) is AccessVerdict.ALLOW
