"""Tests for DDD PresetPackage and FileSystemPresetRepository."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.models.preset.package import AuthoredPlugin, PresetPackage, PresetScope
from lca.infrastructure.preset.fs_repository import FileSystemPresetRepository


def _sample_plugin(name: str = "custom_calc") -> AuthoredPlugin:
    code = f'''
plugin_meta = {{
    "name": "{name}",
    "layer": "behavior",
    "implements": ["Plugin"],
    "capabilities": ["custom.calc"],
    "side_effects": "none",
    "policy_class": "execute",
}}

def factory():
    def _run(x: int, y: int) -> int:
        return x + y
    return _run
'''
    return AuthoredPlugin(
        name=name,
        code=code.strip(),
        capabilities=("custom.calc",),
        side_effects="none",
        policy_class="execute",
    )


def test_save_and_find_private_preset(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)

    repo = FileSystemPresetRepository()
    plugin = _sample_plugin("custom_calc")
    package = PresetPackage(
        preset_id="math_tools",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        description="Private math tools preset",
        plugins=(plugin,),
    )

    preset_dir = repo.save(package, assistant_home=assistant_home)
    assert preset_dir.is_dir()
    assert (preset_dir / "bundle.yaml").is_file()
    assert (preset_dir / "plugins" / "custom_calc.py").is_file()

    # Direct autonomous agent access copy: {assistant_home}/plugins/custom_calc.py
    assert (assistant_home / "plugins" / "custom_calc.py").is_file()

    loaded = repo.find_by_id("math_tools", assistant_home=assistant_home)
    assert loaded is not None
    assert loaded.preset_id == "math_tools"
    assert loaded.scope == PresetScope.PRIVATE
    assert loaded.assistant_id == "asst_arch_01"
    assert len(loaded.plugins) == 1
    assert loaded.plugins[0].name == "custom_calc"
    assert loaded.plugins[0].capabilities == ("custom.calc",)
    assert "def factory():" in loaded.plugins[0].code


def test_list_presets_multi_scope(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)
    shared_root = tmp_path / "shared"
    shared_root.mkdir(parents=True)

    repo = FileSystemPresetRepository(shared_root=shared_root)

    # 1. Private preset for asst_arch_01
    pkg_private = PresetPackage(
        preset_id="private_tools",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        plugins=(_sample_plugin("tool_a"),),
    )
    repo.save(pkg_private, assistant_home=assistant_home)

    # 2. Shared preset
    pkg_shared = PresetPackage(
        preset_id="shared_tools",
        scope=PresetScope.SHARED,
        plugins=(_sample_plugin("tool_b"),),
    )
    repo.save(pkg_shared)

    all_presets = repo.list_presets(assistant_home=assistant_home)
    preset_ids = [p.preset_id for p in all_presets]
    assert "private_tools" in preset_ids
    assert "shared_tools" in preset_ids

    # Listing with scope filter
    private_only = repo.list_presets(assistant_home=assistant_home, scope=PresetScope.PRIVATE)
    assert [p.preset_id for p in private_only] == ["private_tools"]

    shared_only = repo.list_presets(assistant_home=assistant_home, scope=PresetScope.SHARED)
    assert [p.preset_id for p in shared_only] == ["shared_tools"]


def test_path_traversal_prevention(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)
    repo = FileSystemPresetRepository()

    invalid_ids = [
        "../bad_escape",
        "../../etc/passwd",
        "/absolute/path",
        "nested/sub/dir",
        "space in name",
        "invalid$char",
        "",
    ]

    for bad_id in invalid_ids:
        with pytest.raises(ValueError, match=r"Invalid preset_id"):
            repo.find_by_id(bad_id, assistant_home=assistant_home)

        pkg = PresetPackage(
            preset_id=bad_id or "placeholder",
            scope=PresetScope.PRIVATE,
        )
        # Force bad_id onto pkg if validation didn't already reject it
        object.__setattr__(pkg, "preset_id", bad_id)
        with pytest.raises(ValueError, match=r"Invalid preset_id"):
            repo.save(pkg, assistant_home=assistant_home)


def test_delete_preset(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)
    repo = FileSystemPresetRepository()

    pkg = PresetPackage(
        preset_id="to_delete",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        plugins=(_sample_plugin("temp_tool"),),
    )
    repo.save(pkg, assistant_home=assistant_home)
    assert repo.find_by_id("to_delete", assistant_home=assistant_home) is not None
    assert (assistant_home / "plugins" / "temp_tool.py").is_file()

    deleted = repo.delete("to_delete", assistant_home=assistant_home)
    assert deleted is True
    assert repo.find_by_id("to_delete", assistant_home=assistant_home) is None
    # Autonomous standalone copy is cleaned up to prevent ghost plugins
    assert not (assistant_home / "plugins" / "temp_tool.py").is_file()

    # Deleting non-existent returns False
    assert repo.delete("to_delete", assistant_home=assistant_home) is False


def test_delete_preset_preserves_shared_plugin_copies(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)
    repo = FileSystemPresetRepository()

    # Preset 1 and Preset 2 both have shared_tool
    pkg1 = PresetPackage(
        preset_id="preset_1",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        plugins=(_sample_plugin("shared_tool"),),
    )
    pkg2 = PresetPackage(
        preset_id="preset_2",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        plugins=(_sample_plugin("shared_tool"),),
    )
    repo.save(pkg1, assistant_home=assistant_home)
    repo.save(pkg2, assistant_home=assistant_home)

    assert (assistant_home / "plugins" / "shared_tool.py").is_file()

    # Delete preset_1: shared_tool must still exist because preset_2 still references it
    repo.delete("preset_1", assistant_home=assistant_home)
    assert (assistant_home / "plugins" / "shared_tool.py").is_file()

    # Delete preset_2: now shared_tool is truly orphan and gets cleaned up
    repo.delete("preset_2", assistant_home=assistant_home)
    assert not (assistant_home / "plugins" / "shared_tool.py").is_file()
