"""Primary-only default; extra_plane is explicit; no kind switch."""

from __future__ import annotations

import pytest

from lca.contracts.models.core.execution.local_exec import AccessVerdict
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.access.grant import default_access_scope
from lca.infrastructure.runtime_plane.access.policy import decide_access
from lca.infrastructure.runtime_plane.paths.paths import outputs_under, resolve_plane_path
from lca.infrastructure.runtime_plane.resolve.resolve import (
    PlaneBindingError,
    PlaneRequest,
    make_sandbox_ref,
    ref_of,
    resolve_plane_bindings,
)


def _needs_approval(plane: object, path: str) -> bool:
    return (
        decide_access(
            "read_file",
            scope=default_access_scope(plane, "read_file"),  # type: ignore[arg-type]
            plane=plane,  # type: ignore[arg-type]
            paths=[path],
        ).verdict
        is AccessVerdict.NEEDS_APPROVAL
    )


def _machine(**kwargs: str) -> PlaneRef:
    root = kwargs.get("root", "/home/lca-sandbox")
    return PlaneRef(
        id=kwargs.get("id", "dev-1"),
        label=kwargs.get("label", "laptop"),
        kind=PlaneKind.MACHINE,
        root=root,
        outputs_dir=outputs_under(root),
        platform=kwargs.get("platform", "linux"),
        home=kwargs.get("home", "/home/lichao"),
    )


def _sandbox() -> PlaneRef:
    return make_sandbox_ref()


def test_only_sandbox_is_primary() -> None:
    bound = resolve_plane_bindings(None, _sandbox())
    assert bound.primary is not None
    assert bound.primary.kind is PlaneKind.SANDBOX
    assert bound.secondary is None


def test_only_machine_is_primary() -> None:
    bound = resolve_plane_bindings(_machine(), None)
    assert bound.primary is not None
    assert bound.primary.kind is PlaneKind.MACHINE
    assert bound.secondary is None


def test_both_available_defaults_to_sandbox() -> None:
    bound = resolve_plane_bindings(_machine(), _sandbox())
    assert bound.primary is not None
    assert bound.primary.kind is PlaneKind.SANDBOX
    assert bound.secondary is None
    assert ref_of(bound, PlaneKind.MACHINE) is None


def test_explicit_machine_when_both_available() -> None:
    bound = resolve_plane_bindings(_machine(), _sandbox(), PlaneRequest(plane="machine"))
    assert bound.primary is not None
    assert bound.primary.kind is PlaneKind.MACHINE
    assert bound.secondary is None


def test_extra_plane_binds_secondary() -> None:
    bound = resolve_plane_bindings(_machine(), _sandbox(), PlaneRequest(extra_plane="machine"))
    assert bound.primary is not None
    assert bound.primary.kind is PlaneKind.SANDBOX
    assert bound.secondary is not None
    assert bound.secondary.kind is PlaneKind.MACHINE
    assert ref_of(bound, PlaneKind.MACHINE) is bound.secondary


def test_missing_explicit_plane_fails() -> None:
    with pytest.raises(PlaneBindingError):
        resolve_plane_bindings(None, _sandbox(), PlaneRequest(plane="machine"))


def test_same_extra_as_primary_fails() -> None:
    with pytest.raises(PlaneBindingError):
        resolve_plane_bindings(None, _sandbox(), PlaneRequest(extra_plane="sandbox"))


def test_nothing_available() -> None:
    bound = resolve_plane_bindings(None, None)
    assert bound.primary is None
    assert bound.secondary is None


def test_relative_path_joins_root() -> None:
    plane = _machine()
    assert resolve_plane_path("notes.txt", plane) == "/home/lca-sandbox/notes.txt"


def test_absolute_path_not_remapped() -> None:
    plane = _machine()
    assert resolve_plane_path("/mnt/data/x", plane) == "/mnt/data/x"
    assert _needs_approval(plane, "/mnt/data/x")


def test_inside_root_no_approval() -> None:
    plane = _machine()
    assert not _needs_approval(plane, "/home/lca-sandbox/out/a.txt")


def test_tmp_no_approval() -> None:
    plane = _machine()
    assert not _needs_approval(plane, "/tmp/scratch")  # noqa: S108


def test_machine_tools_inject_local_system_role() -> None:
    from types import SimpleNamespace

    from lca.infrastructure.runtime_plane.bindings.bindings import plane_bindings_scope
    from lca.infrastructure.runtime_plane.prompt.assembler import render_plane_prompt
    from lca.infrastructure.runtime_plane.resolve.resolve import PlaneBindings

    plane = _machine()
    with plane_bindings_scope(PlaneBindings(primary=plane)):
        text = render_plane_prompt([SimpleNamespace(name="local_listFiles")])
    assert "lobe-local-system" in text
    assert "/home/lca-sandbox" in text
    assert "reportlab" in text
    assert "CLOUD SANDBOX" not in text


def test_empty_catalog_follows_bound_machine_plane() -> None:
    from lca.infrastructure.runtime_plane.bindings.bindings import plane_bindings_scope
    from lca.infrastructure.runtime_plane.prompt.assembler import render_plane_prompt
    from lca.infrastructure.runtime_plane.resolve.resolve import PlaneBindings

    plane = _machine()
    with plane_bindings_scope(PlaneBindings(primary=plane)):
        text = render_plane_prompt(())
    assert "lobe-local-system" in text
    assert "CLOUD SANDBOX" not in text


def test_dotdot_escape_needs_approval() -> None:
    plane = _machine()
    assert _needs_approval(plane, "/home/lca-sandbox/../.ssh/id_rsa")
    assert _needs_approval(plane, "/tmp/../etc/passwd")  # noqa: S108
