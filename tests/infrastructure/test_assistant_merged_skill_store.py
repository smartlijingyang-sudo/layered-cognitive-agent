"""Tests for assistant-scoped skill store merge and create_skill tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.protocols.assistant.skill_overlay import SkillSource
from lca.infrastructure.skills.assistant.merged_store import AssistantMergedSkillStore
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings
from lca.plugins.assistant.skill.overlay import AssistantSkillOverlayImpl


class _StubCatalog:
    def __init__(self, home: Path) -> None:
        self._home = home

    def get(self, assistant_id: str) -> object:
        from types import SimpleNamespace

        return SimpleNamespace(home_path=str(self._home / assistant_id), assistant_id=assistant_id)


class _StubOverlay(AssistantSkillOverlayImpl):
    pass


@pytest.mark.asyncio
async def test_merged_store_lists_assistant_skills_only(tmp_path: Path) -> None:
    """ADR-0243 D1: assistant-bound 发现只含 Home 技能；全局未挂载技能不出现。"""
    assistant_id = "asst_merge"
    home = tmp_path / assistant_id
    home.mkdir()
    (home / "manifest.json").write_text(
        '{"assistant_id":"asst_merge","digests":{},"revision_seq":0,"schema_version":1}',
        encoding="utf-8",
    )
    (home / "skills").mkdir()
    catalog = _StubCatalog(tmp_path)
    overlay = _StubOverlay(catalog=catalog, event_emitter=None)
    staging = _write_local_skill(tmp_path / "pkg", "assistant-only")
    await overlay.install(assistant_id, SkillSource(local_path=str(staging)), actor="test")

    global_store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "global"))
    global_store.install_package(
        skill_id="global-skill",
        skill_md_text="---\nname: global\ndescription: g\nreferences: []\n---\nbody",
        resource_files={},
        source_url="u",
    )
    merged = AssistantMergedSkillStore(
        global_store=global_store, overlay=overlay, assistant_id=assistant_id
    )
    ids = [entry.skill_id for entry in merged.list_installed()]
    assert ids == ["assistant-only"]
    assert "global-skill" not in ids


@pytest.mark.asyncio
async def test_merged_store_get_does_not_fall_back_to_global(tmp_path: Path) -> None:
    """ADR-0243 I-B16: Home 未挂载的全局技能，get 必须失败而非兜底。"""
    assistant_id = "asst_merge"
    home = tmp_path / assistant_id
    home.mkdir()
    (home / "manifest.json").write_text(
        '{"assistant_id":"asst_merge","digests":{},"revision_seq":0,"schema_version":1}',
        encoding="utf-8",
    )
    (home / "skills").mkdir()
    catalog = _StubCatalog(tmp_path)
    overlay = _StubOverlay(catalog=catalog, event_emitter=None)

    global_store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "global"))
    global_store.install_package(
        skill_id="global-skill",
        skill_md_text="---\nname: global\ndescription: g\nreferences: []\n---\nbody",
        resource_files={},
        source_url="u",
    )
    merged = AssistantMergedSkillStore(
        global_store=global_store, overlay=overlay, assistant_id=assistant_id
    )
    from lca.contracts.protocols.memory.operational_skills import SkillNotFoundError

    with pytest.raises(SkillNotFoundError):
        merged.get("global-skill")


def _write_local_skill(root: Path, skill_id: str) -> Path:
    root.mkdir()
    (root / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: demo\nreferences: []\n---\nbody",
        encoding="utf-8",
    )
    return root
