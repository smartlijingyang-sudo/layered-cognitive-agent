"""Tests for PresetPromotionService (cross-agent sharing and platform export)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.application.preset.promotion import (
    PresetPromotionService,
    PromotionResult,
)
from lca.contracts.models.preset.package import AuthoredPlugin, PresetPackage, PresetScope
from lca.infrastructure.preset.fs_repository import FileSystemPresetRepository


def _sample_plugin(name: str = "arch_checker") -> AuthoredPlugin:
    code = f'''
plugin_meta = {{
    "name": "{name}",
    "layer": "behavior",
    "implements": ["Plugin"],
    "capabilities": ["arch.check"],
    "side_effects": "none",
    "policy_class": "execute",
    "description": "Architecture rule verification",
}}

def factory():
    def {name}(rule: str) -> dict:
        return {{"rule": rule, "status": "pass"}}
    return {name}
'''
    return AuthoredPlugin(
        name=name,
        code=code.strip(),
        capabilities=("arch.check",),
        side_effects="none",
        policy_class="execute",
    )


def test_promote_to_shared(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)
    shared_root = tmp_path / "shared" / "presets"
    shared_root.mkdir(parents=True)

    repo = FileSystemPresetRepository(shared_root=shared_root)
    plugin = _sample_plugin("arch_checker")
    package = PresetPackage(
        preset_id="arch_rules_kit",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        description="Architecture validation kit",
        plugins=(plugin,),
    )
    repo.save(package, assistant_home=assistant_home)

    service = PresetPromotionService(repository=repo, shared_root=shared_root)
    result: PromotionResult = service.promote_to_shared(
        "arch_rules_kit",
        assistant_home=assistant_home,
    )

    assert result.preset_id == "arch_rules_kit"
    assert result.scope == PresetScope.SHARED
    assert result.target_path.is_dir()
    assert (result.target_path / "bundle.yaml").is_file()
    assert (result.target_path / "plugins" / "arch_checker.py").is_file()

    # Metadata & SHA256 integrity check
    meta_path = result.target_path / "preset.json"
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["scope"] == "shared"
    assert meta["assistant_id"] == "asst_arch_01"
    assert "checksum" in meta

    expected_sha = service._calculate_checksum(package)
    assert meta["checksum"] == expected_sha


def test_export_to_platform(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)
    platform_root = tmp_path / "bundles" / "agent-presets"
    platform_root.mkdir(parents=True)

    repo = FileSystemPresetRepository(platform_root=platform_root)
    plugin = _sample_plugin("arch_checker")
    package = PresetPackage(
        preset_id="arch_rules_kit",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        description="Architecture validation kit",
        plugins=(plugin,),
    )
    repo.save(package, assistant_home=assistant_home)

    service = PresetPromotionService(repository=repo, platform_root=platform_root)
    result: PromotionResult = service.export_to_platform(
        "arch_rules_kit",
        assistant_home=assistant_home,
    )

    assert result.preset_id == "arch_rules_kit"
    assert result.scope == PresetScope.PLATFORM
    assert result.target_path.is_dir()
    assert (result.target_path / "bundle.yaml").is_file()

    # Can be read back as platform scope
    loaded = repo.find_by_id("arch_rules_kit", scope=PresetScope.PLATFORM)
    assert loaded is not None
    assert loaded.scope == PresetScope.PLATFORM
    assert len(loaded.plugins) == 1


def test_promote_non_existent_fails_loudly(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)
    service = PresetPromotionService()

    with pytest.raises(FileNotFoundError, match="not found"):
        service.promote_to_shared("non_existent_preset", assistant_home=assistant_home)
