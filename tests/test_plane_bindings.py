"""Primary-only default; extra_plane is explicit; no kind switch."""

from __future__ import annotations

import pytest

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.infrastructure.plane.paths import outputs_under
from lca.infrastructure.plane.resolve import (
    PlaneBindingError,
    PlaneRequest,
    make_sandbox_ref,
    ref_of,
    resolve_plane_bindings,
)
from lca.infrastructure.plane.scope import path_needs_approval, resolve_plane_path


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
    assert path_needs_approval("/mnt/data/x", plane)


def test_inside_root_no_approval() -> None:
    plane = _machine()
    assert not path_needs_approval("/home/lca-sandbox/out/a.txt", plane)


def test_tmp_no_approval() -> None:
    plane = _machine()
    assert not path_needs_approval("/tmp/scratch", plane)  # noqa: S108


def test_machine_tools_inject_local_system_role() -> None:
    from types import SimpleNamespace

    from lca.infrastructure.plane.resolve import PlaneBindings
    from lca.infrastructure.plane.scope import plane_bindings_scope
    from lca.cognition.brain.sandbox_prompt import build_cloud_sandbox_prompt

    plane = _machine()
    with plane_bindings_scope(PlaneBindings(primary=plane)):
        text = build_cloud_sandbox_prompt([SimpleNamespace(name="local_listFiles")])
    assert "lobe-local-system" in text
    assert "/home/lca-sandbox" in text
    assert "reportlab" in text
    assert "CLOUD SANDBOX" not in text


def test_dotdot_escape_needs_approval() -> None:
    plane = _machine()
    assert path_needs_approval("/home/lca-sandbox/../.ssh/id_rsa", plane)
    assert path_needs_approval("/tmp/../etc/passwd", plane)  # noqa: S108
