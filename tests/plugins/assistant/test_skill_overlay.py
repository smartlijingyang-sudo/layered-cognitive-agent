"""assistant.skill_overlay plugin tests(ADR-0187 §7 PR-6)。

覆盖契约:

- install(本地源):写 ``{home}/skills/<skill_id>/`` + manifest skills 索引 +
  ``revision_seq++`` + 发 ``assistant.skill.installed`` EP(四件套)
- install(URL 源):经注入的 fake importer,同一条 0048 落盘管线
- install 失败(缺 SKILL.md / 未知助理 / 拉取失败)⇒ 不写 Home、不发 EP
- activate:仅 VERIFIED/ACTIVE 可激活;未验证 / 未安装拒收(fail-closed)
- list_installed:扫 ``{home}/skills/``;手动落盘目录 = draft
- 跨助理隔离:A 装的 skill 不出现在 B
- plugin Manifest:provides / requires / effects / test_suite / emits 声明
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.capabilities import ASSISTANT_SKILL_OVERLAY
from lca.contracts.observability.assistant_ep_closure import (
    ASSISTANT_REQUIRED_FIELDS,
    ASSISTANT_SKILL_ACTIVATED,
    ASSISTANT_SKILL_INSTALLED,
)
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.contracts.protocols.assistant.skill_overlay import (
    SkillNotInstalled,
    SkillNotVerified,
    SkillSource,
)
from lca.contracts.protocols.declarative.declarative_common import PluginSpecKind
from lca.contracts.protocols.memory.operational_skills import (
    SkillImportError,
    SkillPackage,
)
from lca.harness.plugin_api import definition_from_plugin
from lca.harness.plugin_manifest import EffectClass
from lca.infrastructure.skills.disk_store import DiskSkillPackageStore
from lca.infrastructure.skills.settings import SkillSettings
from lca.plugins.assistant.catalog import (
    AssistantCatalogError,
    AssistantCatalogImpl,
)
from lca.plugins.assistant.skill_overlay import (
    AssistantSkillOverlayImpl,
    Config,
    setup,
)

# ── helpers ─────────────────────────────────────────────────────────


def _make_local_skill(root: Path, *, name: str = "demo-skill") -> Path:
    """物化一个本地 skill 目录(SKILL.md + frontmatter + 资源)。"""
    skill_dir = root / f"{name}-src"
    (skill_dir / "resources").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: demo operational skill\n"
        "---\n"
        "# Demo Skill\n\n按步骤操作。\n",
        encoding="utf-8",
    )
    (skill_dir / "resources" / "reference.md").write_text("ref", encoding="utf-8")
    return skill_dir


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "assistants"


@pytest.fixture
def emitted() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
def catalog(root: Path, emitted: list[tuple[str, dict[str, Any]]]) -> AssistantCatalogImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantCatalogImpl(root=root, event_emitter=_record)


@pytest.fixture
def overlay(
    catalog: AssistantCatalogImpl,
    emitted: list[tuple[str, dict[str, Any]]],
) -> AssistantSkillOverlayImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantSkillOverlayImpl(catalog=catalog, event_emitter=_record)


@pytest.fixture
def handle(catalog: AssistantCatalogImpl) -> Any:
    return catalog.create(CreateAssistantRequest(name="Demo", description="d"))


@pytest.fixture
def local_skill(tmp_path: Path) -> Path:
    return _make_local_skill(tmp_path)


def _read_manifest(home: Path) -> dict[str, Any]:
    return json.loads((home / "manifest.json").read_text(encoding="utf-8"))


# ── SkillSource 契约 ────────────────────────────────────────────────


class TestSkillSource:
    def test_url_and_local_path_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="只能指定"):
            SkillSource(url="https://x.test/s.md", local_path="/tmp/x")  # noqa: S108 - test fixture

    def test_neither_rejected(self) -> None:
        with pytest.raises(ValueError, match="只能指定"):
            SkillSource()

    def test_url_requires_http_prefix(self) -> None:
        with pytest.raises(ValueError, match="http"):
            SkillSource(url="ftp://x.test/skill.zip")

    def test_local_path_requires_absolute(self) -> None:
        with pytest.raises(ValueError, match="绝对路径"):
            SkillSource(local_path="relative/dir")

    def test_reference_returns_active_carrier(self) -> None:
        assert SkillSource(url="https://x.test/s.md").reference == "https://x.test/s.md"
        source = SkillSource(local_path="/tmp/s")  # noqa: S108 - test fixture
        assert source.reference == "/tmp/s"  # noqa: S108 - test fixture


# ── install:本地源 ──────────────────────────────────────────────────


class TestInstallLocalSource:
    async def test_install_writes_home_skills_and_manifest(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
        local_skill: Path,
    ) -> None:
        receipt = await overlay.install(
            handle.assistant_id, SkillSource(local_path=str(local_skill))
        )
        home = Path(handle.home_path)
        installed = home / "skills" / "demo-skill"
        assert (installed / "SKILL.md").is_file()
        assert (installed / "manifest.json").is_file()
        # 资源经 0048 读缝 round-trip(物理布局由 DiskSkillPackageStore 拥有)
        store = DiskSkillPackageStore(SkillSettings(cache_dir=home / "skills"))
        package = store.get("demo-skill")
        assert package.resource_paths == ("resources/reference.md",)
        assert store.read_resource("demo-skill", "resources/reference.md").strip() == "ref"

        manifest = _read_manifest(home)
        assert manifest["revision_seq"] == 1
        assert manifest["digests"]["skills/demo-skill"] == receipt.digest
        entry = manifest["skills"]["demo-skill"]
        assert entry["artifact_state"] == "verified"
        assert entry["digest"] == receipt.digest

    async def test_install_returns_verified_receipt(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
        local_skill: Path,
    ) -> None:
        receipt = await overlay.install(
            handle.assistant_id, SkillSource(local_path=str(local_skill))
        )
        assert receipt.skill_id == "demo-skill"
        assert receipt.artifact_state == "verified"
        assert receipt.digest.startswith("sha256:")
        assert receipt.revision_seq == 1
        assert receipt.manifest_digest.startswith("sha256:")
        assert receipt.install_path.endswith(str(Path("skills") / "demo-skill"))
        assert receipt.source == str(local_skill)

    async def test_install_emits_installed_ep_with_required_fields(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
        local_skill: Path,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(local_skill)))
        skill_events = [(ep, p) for ep, p in emitted if ep == ASSISTANT_SKILL_INSTALLED]
        assert len(skill_events) == 1
        _, payload = skill_events[0]
        for field_name in ASSISTANT_REQUIRED_FIELDS:
            assert field_name in payload, f"EP payload 缺 {field_name}"
        assert payload["assistant_id"] == handle.assistant_id
        assert payload["revision_seq"] == 1
        assert payload["skill_id"] == "demo-skill"
        assert payload["artifact_state"] == "verified"
        assert payload["actor"] == "system"

    async def test_install_cleans_up_staging(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
        local_skill: Path,
    ) -> None:
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(local_skill)))
        staging = Path(handle.home_path) / "skills" / ".staging"
        assert not staging.exists() or not any(staging.iterdir())

    async def test_install_keeps_catalog_get_green(
        self,
        overlay: AssistantSkillOverlayImpl,
        catalog: AssistantCatalogImpl,
        handle: Any,
        local_skill: Path,
    ) -> None:
        """skills 索引进 digest 后,catalog.get 的 I-A3 校验仍通过。"""
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(local_skill)))
        spec = catalog.get(handle.assistant_id)
        assert spec.revision_seq == 1

    async def test_reinstall_same_skill_keeps_single_copy(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
        local_skill: Path,
    ) -> None:
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(local_skill)))
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(local_skill)))
        home = Path(handle.home_path)
        assert (home / "skills" / "demo-skill" / "SKILL.md").is_file()
        manifest = _read_manifest(home)
        assert manifest["revision_seq"] == 2


# ── install:URL 源(fake importer,无真网络)──────────────────────────


class _StagingUrlImporter:
    """把固定包经 0048 ``install_package`` 落进给定 staging(模拟网络拉取)。"""

    def __init__(self, staging_root: Path, skill_md_text: str) -> None:
        self._store = DiskSkillPackageStore(SkillSettings(cache_dir=staging_root))
        self._text = skill_md_text

    async def import_from_url(self, url: str, *, kind: str = "auto") -> SkillPackage:
        del kind
        return self._store.install_package(
            skill_id="url-skill",
            skill_md_text=self._text,
            resource_files={},
            source_url=url,
            version="1.2.3",
        )


class TestInstallUrlSource:
    async def test_install_from_url_uses_injected_importer(
        self,
        catalog: AssistantCatalogImpl,
        emitted: list[tuple[str, dict[str, Any]]],
        handle: Any,
    ) -> None:
        text = "---\nname: url-skill\ndescription: fetched\n---\nbody\n"

        def _factory(staging_root: Path) -> _StagingUrlImporter:
            return _StagingUrlImporter(staging_root, text)

        def _record(event: str, payload: Mapping[str, Any]) -> None:
            emitted.append((event, dict(payload)))

        overlay = AssistantSkillOverlayImpl(
            catalog=catalog, event_emitter=_record, url_importer_factory=_factory
        )
        receipt = await overlay.install(
            handle.assistant_id, SkillSource(url="https://example.com/skill.md")
        )
        assert receipt.skill_id == "url-skill"
        assert receipt.version == "1.2.3"
        assert receipt.artifact_state == "verified"
        assert (Path(handle.home_path) / "skills" / "url-skill" / "SKILL.md").is_file()
        assert any(ep == ASSISTANT_SKILL_INSTALLED for ep, _ in emitted)


# ── install:失败路径(不写 Home、不发 EP)──────────────────────────


class TestInstallFailClosed:
    async def test_local_source_without_skill_md_rejected(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
        tmp_path: Path,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        empty = tmp_path / "no-skill"
        empty.mkdir()
        with pytest.raises(SkillImportError):
            await overlay.install(handle.assistant_id, SkillSource(local_path=str(empty)))
        home = Path(handle.home_path)
        assert list((home / "skills").iterdir()) == []
        assert not any(ep == ASSISTANT_SKILL_INSTALLED for ep, _ in emitted)
        assert _read_manifest(home)["revision_seq"] == 0

    async def test_unknown_assistant_rejected(
        self,
        overlay: AssistantSkillOverlayImpl,
        local_skill: Path,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        with pytest.raises(AssistantCatalogError):
            await overlay.install("asst_missing", SkillSource(local_path=str(local_skill)))
        assert emitted == []

    async def test_url_fetch_failure_leaves_home_untouched(
        self,
        catalog: AssistantCatalogImpl,
        emitted: list[tuple[str, dict[str, Any]]],
        handle: Any,
    ) -> None:
        class _BoomImporter:
            async def import_from_url(self, url: str, *, kind: str = "auto") -> SkillPackage:
                raise SkillImportError(f"下载失败: {url}")

        def _record(event: str, payload: Mapping[str, Any]) -> None:
            emitted.append((event, dict(payload)))

        overlay = AssistantSkillOverlayImpl(
            catalog=catalog,
            event_emitter=_record,
            url_importer_factory=lambda _root: _BoomImporter(),  # type: ignore[return-value]
        )
        with pytest.raises(SkillImportError):
            await overlay.install(handle.assistant_id, SkillSource(url="https://example.com/x.md"))
        home = Path(handle.home_path)
        assert list((home / "skills").iterdir()) == []
        assert not any(ep == ASSISTANT_SKILL_INSTALLED for ep, _ in emitted)


# ── activate ────────────────────────────────────────────────────────


class TestActivate:
    async def test_activate_verified_skill_emits_ep(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
        local_skill: Path,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(local_skill)))
        receipt = overlay.activate(handle.assistant_id, "demo-skill", actor="user:test")
        assert receipt.skill_id == "demo-skill"
        assert receipt.artifact_state == "verified"
        assert receipt.actor == "user:test"
        assert receipt.revision_seq == 1
        activated = [(ep, p) for ep, p in emitted if ep == ASSISTANT_SKILL_ACTIVATED]
        assert len(activated) == 1
        _, payload = activated[0]
        for field_name in ASSISTANT_REQUIRED_FIELDS:
            assert field_name in payload, f"EP payload 缺 {field_name}"
        assert payload["skill_id"] == "demo-skill"
        assert payload["actor"] == "user:test"

    async def test_activate_does_not_mutate_home(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
        local_skill: Path,
    ) -> None:
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(local_skill)))
        home = Path(handle.home_path)
        before = _read_manifest(home)
        overlay.activate(handle.assistant_id, "demo-skill")
        assert _read_manifest(home) == before

    async def test_activate_unknown_skill_raises(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
    ) -> None:
        with pytest.raises(SkillNotInstalled):
            overlay.activate(handle.assistant_id, "never-installed")

    async def test_activate_unverified_package_rejected(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
    ) -> None:
        """手动落盘(未过 0067 闸)的包不可 activate(ADR-0187 §3 D6)。"""
        home = Path(handle.home_path)
        rogue = home / "skills" / "rogue-skill"
        rogue.mkdir(parents=True)
        (rogue / "SKILL.md").write_text("unverified", encoding="utf-8")
        with pytest.raises(SkillNotVerified):
            overlay.activate(handle.assistant_id, "rogue-skill")

    async def test_activate_unknown_assistant_rejected(
        self,
        overlay: AssistantSkillOverlayImpl,
    ) -> None:
        with pytest.raises(AssistantCatalogError):
            overlay.activate("asst_missing", "demo-skill")


# ── list_installed ──────────────────────────────────────────────────


class TestListInstalled:
    async def test_list_empty_when_nothing_installed(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
    ) -> None:
        assert overlay.list_installed(handle.assistant_id) == ()

    async def test_list_returns_verified_receipt(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
        local_skill: Path,
    ) -> None:
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(local_skill)))
        receipts = overlay.list_installed(handle.assistant_id)
        assert len(receipts) == 1
        assert receipts[0].skill_id == "demo-skill"
        assert receipts[0].artifact_state == "verified"

    async def test_list_marks_manually_dropped_package_draft(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
    ) -> None:
        home = Path(handle.home_path)
        rogue = home / "skills" / "rogue-skill"
        rogue.mkdir(parents=True)
        (rogue / "SKILL.md").write_text("unverified", encoding="utf-8")
        receipts = overlay.list_installed(handle.assistant_id)
        assert len(receipts) == 1
        assert receipts[0].artifact_state == "draft"

    async def test_list_sorted_by_skill_id(
        self,
        overlay: AssistantSkillOverlayImpl,
        handle: Any,
        tmp_path: Path,
    ) -> None:
        for name in ("zeta-skill", "alpha-skill"):
            skill = _make_local_skill(tmp_path / name, name=name)
            await overlay.install(handle.assistant_id, SkillSource(local_path=str(skill)))
        receipts = overlay.list_installed(handle.assistant_id)
        assert [r.skill_id for r in receipts] == ["alpha-skill", "zeta-skill"]


# ── 跨助理隔离 ──────────────────────────────────────────────────────


class TestCrossAssistantIsolation:
    async def test_installed_skill_not_visible_to_other_assistant(
        self,
        overlay: AssistantSkillOverlayImpl,
        catalog: AssistantCatalogImpl,
        handle: Any,
        local_skill: Path,
    ) -> None:
        other = catalog.create(CreateAssistantRequest(name="Other"))
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(local_skill)))
        assert overlay.list_installed(other.assistant_id) == ()
        with pytest.raises(SkillNotInstalled):
            overlay.activate(other.assistant_id, "demo-skill")

    async def test_install_into_other_assistant_home_is_independent(
        self,
        overlay: AssistantSkillOverlayImpl,
        catalog: AssistantCatalogImpl,
        handle: Any,
        local_skill: Path,
    ) -> None:
        other = catalog.create(CreateAssistantRequest(name="Other"))
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(local_skill)))
        await overlay.install(other.assistant_id, SkillSource(local_path=str(local_skill)))
        for home_path in (handle.home_path, other.home_path):
            staging = Path(home_path) / "skills" / ".staging"
            assert not staging.exists() or not any(staging.iterdir())
            assert (Path(home_path) / "skills" / "demo-skill").is_dir()


# ── Plugin Manifest 形状 ────────────────────────────────────────────


class TestPluginManifest:
    def test_definition_id_namespace(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.id == "lca.plugins.assistant.skill_overlay"

    def test_provides_assistant_skill_overlay(self) -> None:
        definition = definition_from_plugin(setup)
        assert ASSISTANT_SKILL_OVERLAY.key in definition.provided_capability_keys

    def test_requires_catalog_and_event_bus(self) -> None:
        definition = definition_from_plugin(setup)
        required = set(definition.required_capability_keys)
        assert {"assistant.catalog", "event.bus"}.issubset(required)

    def test_layer_and_kind(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.layer == "L4"
        assert definition.spec.kind is PluginSpecKind.PROVIDER

    def test_effects_is_filesystem_only(self) -> None:
        """capability_plan_resolver 禁止多 effect class(单类裁决);网络拉取
        属 0048 ``SkillImporter`` 的 effect 面,本插件自身持久副作用 = Home 写。"""
        definition = definition_from_plugin(setup)
        assert EffectClass.FILESYSTEM in definition.spec.effects
        assert len(definition.spec.effects) == 1

    def test_test_suite_path_matches(self) -> None:
        definition = definition_from_plugin(setup)
        assert (
            definition.spec.verification.test_suite
            == "tests/plugins/assistant/test_skill_overlay.py"
        )

    def test_ownership_emits_install_and_activate_eps(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.ownership is not None
        assert ASSISTANT_SKILL_INSTALLED in definition.ownership.emits
        assert ASSISTANT_SKILL_ACTIVATED in definition.ownership.emits

    def test_config_rejects_extra_keys(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Config.model_validate({"unexpected": "x"})
