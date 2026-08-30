"""Preinstall prompt is YAML notes + catalog tuples, not if/append prose."""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.core.plane import PlaneKind
from lca.infrastructure.plane.preinstall_prompt import render_preinstalled_block
from lca.infrastructure.sandbox.surface import plane_system_role


def test_yaml_is_the_note_ssot() -> None:
    text = Path("lca/infrastructure/plane/prompts/preinstall.yaml").read_text(encoding="utf-8")
    assert "STSong-Light" in text
    assert "UnicodeCIDFont" in text
    assert "machine:" in text
    assert "sandbox:" in text


def test_machine_block_from_yaml() -> None:
    block = render_preinstalled_block(plane=PlaneKind.MACHINE)
    assert "Host machine" in block
    assert "STSong-Light" in block
    assert "no TTF hunt" in block
    assert "runCommand" in block
    assert "executeCode" in block
    assert "reportlab" in block


def test_sandbox_block_shares_font_note() -> None:
    block = render_preinstalled_block(plane=PlaneKind.SANDBOX)
    assert "Cloud sandbox" in block
    assert "STSong-Light" in block
    assert "executeCode" in block


def test_machine_system_role_embeds_yaml_notes() -> None:
    from lca.contracts.models.core.plane import PlaneRef

    role = plane_system_role(
        PlaneRef(
            id="dev-1",
            label="box",
            kind=PlaneKind.MACHINE,
            root="/home/sandbox-user",
            outputs_dir="/home/sandbox-user/outputs",
            platform="linux",
        )
    )
    assert "STSong-Light" in role
    assert "/mnt/data" not in role
