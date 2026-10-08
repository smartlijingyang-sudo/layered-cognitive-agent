"""ADR-0243 PR-2/PR-3 测试：全局技能硬链接物化、COW 编辑、继承快照、显式 re-link。

覆盖：

- ``catalog.create(initial_skills=...)``：硬链接物化到 ``{home}/skills/``、
  manifest ``skills`` 索引带 ``source: global_link``、revision_seq 仍为 0
- ``skill_overlay.edit``：COW 断链（全局文件不变）、新 SKILL.md 落盘、
  ``source`` 变 ``local``、manifest 修订 + ``assistant.profile.revised`` EP
- ``inherit_from``：继承 ``global_link`` 技能保持硬链接 + 来源标记
- ``remove``：删除 global_link 后全局技能不受影响，merged store 不再列出
- ``relink_global_skills``：D1「显式 re-link 才升级」—— stale 包重链到全局
  当前 inode、``local`` 与全局缺失/退役的包不动、整批一次修订、不写全局库
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.observability.closure.assistant_ep_closure import (
    ASSISTANT_PROFILE_REVISED,
    ASSISTANT_REQUIRED_FIELDS,
    ASSISTANT_SKILL_INSTALLED,
)
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.contracts.protocols.assistant.skill_overlay import SkillSource
from lca.infrastructure.skills.assistant.merged_store import AssistantMergedSkillStore
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings
from lca.plugins.assistant.skill.overlay import AssistantSkillOverlayImpl
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl

# 摘要取 ``_package_digest``（= 含 frontmatter 的 SKILL.md 全文 sha256），
# 不是落盘 body 的文件摘要；写死字面值以钉住这个约定。
_GLOBAL_V2_DIGEST = "sha256:2c68f9993ee635c19d15a6bb8f41a9b905c0ce49fc6e3a27286fad4cec81e836"
_SECOND_V2_DIGEST = "sha256:9c1339e16009284df5279bb91cc682c76ef203fec46716aa94bcf5397d99d622"


def _global_skill_text(skill_id: str, body: str) -> str:
    return (
        "---\n"
        f"name: {skill_id}\n"
        "description: global demo\n"
        "references: []\n"
        "---\n"
        f"# Global Skill\n\n{body}\n"
    )


def _install_global_skill(
    store: DiskSkillPackageStore,
    skill_id: str = "global-skill",
    body: str = "原始内容。",
    version: str = "1.0.0",
) -> None:
    """写入 / 刷新全局包。

    ``install_package`` 先 unlink 再写新文件，所以刷新会让已链接 Home 停在旧
    inode —— 这正是 re-link 存在的理由（ADR-0243 D1）。
    """
    store.install_package(
        skill_id=skill_id,
        skill_md_text=_global_skill_text(skill_id, body),
        resource_files={},
        source_url=f"https://example.com/{skill_id}",
        version=version,
    )


def _skill_md(skill_dir: Path) -> str:
    return (skill_dir / "SKILL.md").read_text(encoding="utf-8")


def _tree_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    """目录树每个文件的 ``{相对路径: (内容, inode)}``。"""
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_ino)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _forbidden_global_store() -> DiskSkillPackageStore:
    raise AssertionError("无 global_link 条目时不得解析全局库根")


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
    global_store: DiskSkillPackageStore,
    emitted: list[tuple[str, dict[str, Any]]],
) -> AssistantSkillOverlayImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantSkillOverlayImpl(
        catalog=catalog,
        event_emitter=_record,
        global_store_factory=lambda: global_store,
    )


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

    def test_create_defaults_to_all_global_skills(
        self,
        catalog: AssistantCatalogImpl,
        global_store: DiskSkillPackageStore,
    ) -> None:
        """空 initial_skills = 默认物化全部全局技能（ADR-0243 I-B14）。"""
        handle = catalog.create(CreateAssistantRequest(name="Demo", description="d"))
        home = Path(handle.home_path)
        skill_dir = home / "skills" / "global-skill"
        assert (skill_dir / "SKILL.md").is_file()
        assert (skill_dir / "manifest.json").is_file()
        meta = json.loads((skill_dir / "manifest.json").read_text(encoding="utf-8"))
        assert meta["source"] == "global_link"
        manifest = _read_manifest(home)
        entry = manifest["skills"]["global-skill"]
        assert entry["source"] == "global_link"
        assert manifest["digests"]["skills/global-skill"] == entry["digest"]

    def test_create_without_global_store_keeps_empty_skills(self, root: Path) -> None:
        """全局库不可用时，空 initial_skills 不失败，skills/ 保持为空。"""
        catalog = AssistantCatalogImpl(root=root, event_emitter=None)
        handle = catalog.create(CreateAssistantRequest(name="Demo", description="d"))
        home = Path(handle.home_path)
        skills_dir = home / "skills"
        assert skills_dir.is_dir()
        assert list(skills_dir.glob("*/SKILL.md")) == []


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


class TestRelinkGlobalSkills:
    """ADR-0243 D1「显式 re-link 才升级」：全局刷新后 Home 停在旧 inode。"""

    def test_stale_global_link_relinked_to_current_global(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        global_store: DiskSkillPackageStore,
    ) -> None:
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        home = Path(handle.home_path)
        skill_dir = home / "skills" / "global-skill"
        stale_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        _install_global_skill(global_store, body="新版本内容。", version="2.0.0")

        report = overlay.relink_global_skills(handle.assistant_id, actor="ops:relink")

        assert report.relinked == ("global-skill",)
        assert report.already_current == ()
        assert report.skipped_local == ()
        assert report.skipped_missing_global == ()
        current_md = (global_store.root / "global-skill" / "SKILL.md").read_text(encoding="utf-8")
        assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == current_md
        assert current_md != stale_md
        assert (skill_dir / "SKILL.md").stat().st_ino == (
            global_store.root / "global-skill" / "SKILL.md"
        ).stat().st_ino

        manifest = _read_manifest(home)
        assert report.revision_seq == manifest["revision_seq"] == 1
        assert report.manifest_digest == manifest["manifest_digest"]
        assert manifest["digests"]["skills/global-skill"] == _GLOBAL_V2_DIGEST
        entry = manifest["skills"]["global-skill"]
        assert entry["digest"] == _GLOBAL_V2_DIGEST
        assert entry["source"] == "global_link"
        assert entry["version"] == "2.0.0"
        assert entry["artifact_state"] == "verified"
        assert entry["actor"] == "ops:relink"
        # 包内来源标记保留：继承路径靠它决定硬链接 vs 快照复制
        meta = json.loads((skill_dir / "manifest.json").read_text(encoding="utf-8"))
        assert meta["source"] == "global_link"
        assert meta["version"] == "2.0.0"

    async def test_local_copies_left_byte_identical(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        global_store: DiskSkillPackageStore,
        tmp_path: Path,
    ) -> None:
        """COW 后的 ``local`` 与 install 源条目都不许被全局版本覆盖。"""
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        home = Path(handle.home_path)
        await overlay.edit(
            handle.assistant_id,
            "global-skill",
            _global_skill_text("global-skill", "助理私有改写。"),
            actor="agent",
        )
        own_src = tmp_path / "own-skill-src"
        own_src.mkdir()
        (own_src / "SKILL.md").write_text(
            "---\nname: own-skill\ndescription: d\nreferences: []\n---\n自有技能。\n",
            encoding="utf-8",
        )
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(own_src)))
        edited_dir = home / "skills" / "global-skill"
        before = _tree_snapshot(home / "skills")
        revision_before = _read_manifest(home)["revision_seq"]
        _install_global_skill(global_store, body="新版本内容。", version="2.0.0")

        report = overlay.relink_global_skills(handle.assistant_id)

        assert report.relinked == ()
        assert report.skipped_local == ("global-skill", "own-skill")
        assert report.revision_seq == revision_before == 2
        assert _tree_snapshot(home / "skills") == before
        assert "助理私有改写。" in (edited_dir / "SKILL.md").read_text(encoding="utf-8")
        assert _read_manifest(home)["skills"]["global-skill"]["source"] == "local"

    def test_already_current_writes_nothing(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        home = Path(handle.home_path)
        manifest_bytes = (home / "manifest.json").read_bytes()
        inode = (home / "skills" / "global-skill" / "SKILL.md").stat().st_ino
        emitted.clear()

        report = overlay.relink_global_skills(handle.assistant_id)

        assert report.already_current == ("global-skill",)
        assert report.relinked == ()
        assert report.revision_seq == 0
        assert (home / "manifest.json").read_bytes() == manifest_bytes
        assert sorted(p.name for p in (home / "revisions").iterdir()) == ["0.json"]
        assert (home / "skills" / "global-skill" / "SKILL.md").stat().st_ino == inode
        assert emitted == []

    def test_two_stale_packages_produce_one_revision(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        global_store: DiskSkillPackageStore,
    ) -> None:
        _install_global_skill(global_store, "second-skill")
        handle = catalog.create(
            CreateAssistantRequest(
                name="Demo",
                description="d",
                initial_skills=("global-skill", "second-skill"),
            )
        )
        home = Path(handle.home_path)
        _install_global_skill(global_store, "global-skill", body="新版本内容。", version="2.0.0")
        _install_global_skill(global_store, "second-skill", body="第二个技能 v2。", version="2.0.0")

        report = overlay.relink_global_skills(handle.assistant_id)

        assert report.relinked == ("global-skill", "second-skill")
        assert report.revision_seq == 1
        assert sorted(p.name for p in (home / "revisions").iterdir()) == ["0.json", "1.json"]
        manifest = _read_manifest(home)
        assert manifest["digests"]["skills/global-skill"] == _GLOBAL_V2_DIGEST
        assert manifest["digests"]["skills/second-skill"] == _SECOND_V2_DIGEST

    def test_missing_global_package_skipped_and_home_kept(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        global_store: DiskSkillPackageStore,
    ) -> None:
        """全局包消失不是删除授权：Home 落盘与索引条目原样保留（ADR-0243 §63）。"""
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        home = Path(handle.home_path)
        skill_dir = home / "skills" / "global-skill"
        before = _tree_snapshot(skill_dir)
        entry_before = _read_manifest(home)["skills"]["global-skill"]
        shutil.rmtree(global_store.root / "global-skill")

        report = overlay.relink_global_skills(handle.assistant_id)

        assert report.skipped_missing_global == ("global-skill",)
        assert report.relinked == ()
        assert report.revision_seq == 0
        assert _tree_snapshot(skill_dir) == before
        assert _read_manifest(home)["skills"]["global-skill"] == entry_before

    def test_retired_global_package_skipped(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        global_store: DiskSkillPackageStore,
    ) -> None:
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        home = Path(handle.home_path)
        _install_global_skill(global_store, body="新版本内容。", version="2.0.0")
        global_store.update_package_meta("global-skill", retired=True)
        stale_md = _skill_md(home / "skills" / "global-skill")

        report = overlay.relink_global_skills(handle.assistant_id)

        assert report.skipped_missing_global == ("global-skill",)
        assert report.relinked == ()
        assert report.revision_seq == 0
        assert _skill_md(home / "skills" / "global-skill") == stale_md

    def test_relink_does_not_write_global_store(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        global_store: DiskSkillPackageStore,
    ) -> None:
        """全局库是只读内容源：``source`` 标记不得穿硬链接写回全局包。"""
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        _install_global_skill(global_store, body="新版本内容。", version="2.0.0")
        before = _tree_snapshot(global_store.root)

        report = overlay.relink_global_skills(handle.assistant_id)

        assert report.relinked == ("global-skill",)
        assert _tree_snapshot(global_store.root) == before

    def test_unindexed_directory_untouched_and_unreported(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        global_store: DiskSkillPackageStore,
    ) -> None:
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        rogue = Path(handle.home_path) / "skills" / "rogue-dir"
        rogue.mkdir(parents=True)
        (rogue / "SKILL.md").write_text("手动落盘", encoding="utf-8")
        _install_global_skill(global_store, body="新版本内容。", version="2.0.0")

        report = overlay.relink_global_skills(handle.assistant_id)

        assert report.relinked == ("global-skill",)
        listed = (
            report.relinked
            + report.already_current
            + report.skipped_local
            + report.skipped_missing_global
        )
        assert "rogue-dir" not in listed
        assert (rogue / "SKILL.md").read_text(encoding="utf-8") == "手动落盘"

    def test_missing_home_package_relinked_back(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        global_store: DiskSkillPackageStore,
    ) -> None:
        """索引条目在、落盘目录被手删 ⇒ 重链补齐，重跑收敛到同一终态。"""
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        home = Path(handle.home_path)
        shutil.rmtree(home / "skills" / "global-skill")

        report = overlay.relink_global_skills(handle.assistant_id)

        assert report.relinked == ("global-skill",)
        assert (home / "skills" / "global-skill" / "SKILL.md").read_text(encoding="utf-8") == (
            global_store.root / "global-skill" / "SKILL.md"
        ).read_text(encoding="utf-8")

    def test_emits_one_installed_ep_per_relinked_skill(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
        global_store: DiskSkillPackageStore,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        _install_global_skill(global_store, "second-skill")
        handle = catalog.create(
            CreateAssistantRequest(
                name="Demo",
                description="d",
                initial_skills=("global-skill", "second-skill"),
            )
        )
        _install_global_skill(global_store, "global-skill", body="新版本内容。", version="2.0.0")
        emitted.clear()

        report = overlay.relink_global_skills(handle.assistant_id, actor="ops:relink")

        events = [payload for ep, payload in emitted if ep == ASSISTANT_SKILL_INSTALLED]
        assert len(events) == 1
        payload = events[0]
        for field_name in ASSISTANT_REQUIRED_FIELDS:
            assert field_name in payload, f"EP payload 缺 {field_name}"
        assert payload["skill_id"] == "global-skill"
        assert payload["revision_seq"] == report.revision_seq == 1
        assert payload["manifest_digest"] == report.manifest_digest
        assert payload["actor"] == "ops:relink"
        assert payload["skill_digest"] == _GLOBAL_V2_DIGEST
        assert payload["artifact_state"] == "verified"
        assert payload["source"] == "global_link"
        assert payload["version"] == "2.0.0"

    async def test_no_global_link_never_resolves_global_store(
        self,
        catalog: AssistantCatalogImpl,
        overlay: AssistantSkillOverlayImpl,
    ) -> None:
        """无 ``global_link`` 条目 ⇒ 不构造全局 store（构造会 mkdir 全局根）。"""
        handle = catalog.create(
            CreateAssistantRequest(name="Demo", description="d", initial_skills=("global-skill",))
        )
        await overlay.remove(handle.assistant_id, "global-skill")
        strict = AssistantSkillOverlayImpl(
            catalog=catalog, global_store_factory=_forbidden_global_store
        )

        report = strict.relink_global_skills(handle.assistant_id)

        assert report.relinked == ()
        assert report.already_current == ()
        assert report.skipped_local == ()
        assert report.skipped_missing_global == ()
