"""Primary plane drives prompt. Host no longer pretends to be /mnt/data."""

from __future__ import annotations

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.resolve import PlaneBindings
from lca.infrastructure.runtime_plane.scope import plane_bindings_scope
from lca.infrastructure.sandbox.factory import set_sandbox_resolver
from lca.infrastructure.sandbox.surface import environment_note, skill_preamble


def test_machine_prompt_uses_real_root() -> None:
    plane = PlaneRef(
        id="dev-1",
        label="laptop",
        kind=PlaneKind.MACHINE,
        root="/home/lca-sandbox",
        outputs_dir="/home/lca-sandbox/outputs",
        platform="linux",
    )
    with plane_bindings_scope(PlaneBindings(primary=plane)):
        note = environment_note()
        assert "/home/lca-sandbox" in note
        assert "CLOUD SANDBOX" not in note
        assert "/mnt/data" not in note
        assert "STSong-Light" in note
        assert "outputs/" in skill_preamble()
        assert "/mnt/data" not in skill_preamble()


def test_onlyboxes_prompt_default() -> None:
    set_sandbox_resolver(lambda: None)
    try:
        note = environment_note()
        assert "CLOUD SANDBOX" in note
    finally:
        set_sandbox_resolver(None)
