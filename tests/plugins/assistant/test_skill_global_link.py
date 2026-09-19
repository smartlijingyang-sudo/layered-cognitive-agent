"""ADR-0243 PR-2/PR-3 测试：全局技能硬链接物化、COW 编辑、继承快照。

覆盖：

- ``catalog.create(initial_skills=...)``：硬链接物化到 ``{home}/skills/``、
  manifest ``skills`` 索引带 ``source: global_link``、revision_seq 仍为 0
- ``skill_overlay.edit``：COW 断链（全局文件不变）、新 SKILL.md 落盘、
  ``source`` 变 ``local``、manifest 修订 + ``assistant.profile.revised`` EP
- ``inherit_from``：继承 ``global_link`` 技能保持硬链接 + 来源标记
- ``remove``：删除 global_link 后全局技能不受影响，merged store 不再列出
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.observability.closure.assistant_ep_closure import (
    ASSISTANT_PROFILE_REVISED,
)
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.infrastructure.skills.assistant.merged_store import AssistantMergedSkillStore
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings
from lca.plugins.assistant.skill.overlay import AssistantSkillOverlayImpl
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl


def _install_global_skill(store: DiskSkillPackageStore, skill_id: str = "global-skill") -> None:
    store.install_package(
        skill_id=skill_id,
        skill_md_text=(
            "---\n"
            f"name: {skill_id}\n"
            "description: global demo\n"
            "references: []\n"
            "---\n"
            "# Global Skill\n\n原始内容。\n"
        ),
        resource_files={},
        source_url="https://example.com/global-skill",
        version="1.0.0",
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "assistants"


@pytest.fixture
def emitted() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
def global_store(tmp_path: Path) -> DiskSkillPackageStore:
    store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "global-skills"))
    _install_global_skill(store)
    return store


@pytest.fixture
def catalog(
    root: Path,
    global_store: DiskSkillPackageStore,
    emitted: list[tuple[str, dict[str, Any]]],
) -> AssistantCatalogImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantCatalogImpl(
        root=root, event_emitter=_record, global_skills_store=global_store
    )


@pytest.fixture
def overlay(
    catalog: AssistantCatalogImpl,
    emitted: list[tuple[str, dict[str, Any]]],
) -> AssistantSkillOverlayImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantSkillOverlayImpl(catalog=catalog, event_emitter=_record)


def _read_manifest(home: Path) -> dict[str, Any]:
    return json.loads((home / "manifest.json").read_text(encoding="utf-8"))


class TestCreateMaterializesGlobalSkills:
    def test_create_with_initial_skills_hardlinks(
        self,
        catalog: AssistantCatalogImpl,
        global_store: DiskSkillPackageStore,
    ) -> None:
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        home = Path(handle.home_path)
        skill_dir = home / "skills" / "global-skill"
        assert (skill_dir / "SKILL.md").is_file()
        assert (skill_dir / "manifest.json").is_file()
        # 硬链接：与全局文件同 inode
        assert (
            os.stat(skill_dir / "SKILL.md").st_ino
            == os.stat(global_store.root / "global-skill" / "SKILL.md").st_ino
        )
        # 来源标记
        meta = json.loads((skill_dir / "manifest.json").read_text(encoding="utf-8"))
        assert meta["source"] == "global_link"
        # Home manifest 索引
        manifest = _read_manifest(home)
        assert manifest["revision_seq"] == 0
        entry = manifest["skills"]["global-skill"]
        assert entry["source"] == "global_link"
        assert entry["artifact_state"] == "verified"
        assert manifest["digests"]["skills/global-skill"] == entry["digest"]

    def test_create_initial_skills_requires_global_store(self, root: Path) -> None:
        catalog = AssistantCatalogImpl(root=root, event_emitter=None)
        with pytest.raises(Exception, match="全局技能库"):
            catalog.create(
                CreateAssistantRequest(
                    name="Demo", description="d", initial_skills=("global-skill",)
                )
            )


class TestEditCow:
    async def test_edit_breaks_hardlink_and_keeps_global(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        global_store: DiskSkillPackageStore,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        home = Path(handle.home_path)
        skill_dir = home / "skills" / "global-skill"
        global_skill_md = global_store.root / "global-skill" / "SKILL.md"
        original_global = global_skill_md.read_text(encoding="utf-8")

        new_md = (
            "---\n"
            "name: global-skill\n"
            "description: edited\n"
            "references: []\n"
            "---\n"
            "# Global Skill\n\n编辑后的私有副本。\n"
        )
        receipt = await overlay.edit(handle.assistant_id, "global-skill", new_md, actor="agent")

        # 全局文件未被修改
        assert global_skill_md.read_text(encoding="utf-8") == original_global
        # Home 内容已更新
        assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") != original_global
        # 已断链（新 inode）
        assert (
            os.stat(skill_dir / "SKILL.md").st_ino
            != os.stat(global_store.root / "global-skill" / "SKILL.md").st_ino
        )
        # 来源变 local
        meta = json.loads((skill_dir / "manifest.json").read_text(encoding="utf-8"))
        assert meta["source"] == "local"
        assert receipt.source == "local"
        # manifest 修订 + EP
        manifest = _read_manifest(home)
        assert manifest["revision_seq"] == 1
        assert manifest["skills"]["global-skill"]["source"] == "local"
        assert any(ep == ASSISTANT_PROFILE_REVISED for ep, _ in emitted)

    async def test_edit_unknown_skill_raises(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
    ) -> None:
        handle = catalog.create(CreateAssistantRequest(name="Demo", description="d"))
        with pytest.raises(Exception, match="未安装"):
            await overlay.edit(handle.assistant_id, "missing", "---\nname: x\n---\nbody")


class TestInheritance:
    def test_inherit_preserves_global_link(
        self,
        catalog: AssistantCatalogImpl,
        global_store: DiskSkillPackageStore,
    ) -> None:
        a = catalog.create(
            CreateAssistantRequest(name="A", description="d", initial_skills=("global-skill",))
        )
        b = catalog.create(CreateAssistantRequest(name="B", description="d", inherit_from=a.assistant_id))
        b_home = Path(b.home_path)
        skill_dir = b_home / "skills" / "global-skill"
        assert (skill_dir / "SKILL.md").is_file()
        # 继承后仍是硬链接到同一全局 inode
        assert (
            os.stat(skill_dir / "SKILL.md").st_ino
            == os.stat(global_store.root / "global-skill" / "SKILL.md").st_ino
        )
        meta = json.loads((skill_dir / "manifest.json").read_text(encoding="utf-8"))
        assert meta["source"] == "global_link"
        manifest = _read_manifest(b_home)
        assert manifest["skills"]["global-skill"]["source"] == "global_link"


class TestRemoveGlobalLink:
    async def test_remove_does_not_touch_global(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        global_store: DiskSkillPackageStore,
    ) -> None:
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        global_md = global_store.root / "global-skill" / "SKILL.md"
        original = global_md.read_text(encoding="utf-8")
        await overlay.remove(handle.assistant_id, "global-skill")
        assert global_md.read_text(encoding="utf-8") == original
        assert not (Path(handle.home_path) / "skills" / "global-skill").exists()

        # merged store 不再列出已删除技能（Home-only 语义）
        merged = AssistantMergedSkillStore(
            global_store=global_store,
            overlay=overlay,
            assistant_id=handle.assistant_id,
        )
        assert [e.skill_id for e in merged.list_installed()] == []
