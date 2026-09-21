"""Execution-plane prompt strategy tests (ADR plan A)."""

from __future__ import annotations

from types import SimpleNamespace

from lca.contracts.models.core.state.plane import PlaneBindings, PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.prompt.assembler import render_plane_prompt
from lca.infrastructure.runtime_plane.scope.scope import plane_bindings_scope


def _machine() -> PlaneRef:
    return PlaneRef(
        id="m-lipcmain",
        label="lipcmain",
        kind=PlaneKind.MACHINE,
        root="/home/lca-sandbox",
        outputs_dir="/home/lca-sandbox/outputs",
        platform="Windows",
        home="C:\\Users\\li",
    )


def test_unbound_renders_cloud_sandbox() -> None:
    text = render_plane_prompt(())
    assert "lobe-cloud-sandbox" in text
    assert "Cloud Sandbox" in text
    assert "Workspace root" in text


def test_machine_tools_switch_to_local_system_role() -> None:
    with plane_bindings_scope(PlaneBindings(primary=_machine())):
        text = render_plane_prompt([SimpleNamespace(name="local_listFiles")])
    assert "lobe-local-system" in text
    assert "lipcmain" in text
    assert "Working root" in text
    assert "Cloud Sandbox" not in text


def test_empty_catalog_follows_bound_machine_plane() -> None:
    with plane_bindings_scope(PlaneBindings(primary=_machine())):
        text = render_plane_prompt(())
    assert "lobe-local-system" in text
    assert "lipcmain" in text
    assert "Cloud Sandbox" not in text


def test_machine_role_includes_preinstalled_and_home() -> None:
    with plane_bindings_scope(PlaneBindings(primary=_machine())):
        text = render_plane_prompt(())
    assert "Host machine pre-installed software" in text
    assert "User home" in text
    assert "C:\\Users\\li" in text
