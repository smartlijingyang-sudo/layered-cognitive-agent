"""assistant.bootstrap plugin tests(ADR-0187 §7 PR-4)。

覆盖契约:

- plugin Manifest:provides=assistant.bootstrap / requires=assistant.catalog /
  layer=L4 / kind=SEAM / effects=NONE / test_suite 字符串对齐
- BootstrapProjectionService.project(assistant_id):
  * 返回 ContextManifest,5 个 item(SOUL/IDENTITY/USER/AGENTS/goals)
  * 不含 MEMORY 字面(I-A13 + PR-4 新不变量)
  * digest 不一致 ⇒ AssistantDigestMismatch 透传
  * 助理 home 缺失 ⇒ ValueError
- project_home_to_context_manifest(纯函数):
  * SOUL/IDENTITY/USER/AGENTS 内容 ⇒ ContextItem.payload.text
  * goals.yaml list/mapping 解析 ⇒ payload.goals
- 跨助理隔离:助理 A 的 SOUL 不出现在助理 B 的 ContextManifest
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.capabilities import ASSISTANT_BOOTSTRAP, ASSISTANT_CATALOG
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.harness.plugin_api import definition_from_plugin
from lca.harness.plugin_manifest import EffectClass
from lca.plugins.assistant.bootstrap import (
    BootstrapProjection,
    BootstrapProjectionService,
    project_home_to_context_manifest,
    setup,
)
from lca.plugins.assistant.catalog import (
    AssistantCatalogError,
    AssistantCatalogImpl,
    AssistantDigestMismatch,
)

# ── helpers ─────────────────────────────────────────────────────────


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def catalog(root: Path) -> AssistantCatalogImpl:
    return AssistantCatalogImpl(root=root, event_emitter=None)


@pytest.fixture
def assistant_a(catalog: AssistantCatalogImpl) -> Any:
    return catalog.create(
        CreateAssistantRequest(
            name="Alice",
            description="first",
            seed_user_md="I am a coder",
        )
    )


@pytest.fixture
def assistant_b(catalog: AssistantCatalogImpl) -> Any:
    return catalog.create(CreateAssistantRequest(name="Bob", description="second"))


@pytest.fixture
def bootstrap_service(catalog: AssistantCatalogImpl) -> BootstrapProjectionService:
    return BootstrapProjectionService(catalog=catalog)


# ── Plugin Manifest ──────────────────────────────────────────────


class TestPluginManifest:
    def test_definition_id_namespace(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.id == "lca.plugins.assistant.bootstrap"

    def test_provides_assistant_bootstrap(self) -> None:
        definition = definition_from_plugin(setup)
        assert ASSISTANT_BOOTSTRAP.key in definition.provided_capability_keys

    def test_requires_assistant_catalog(self) -> None:
        definition = definition_from_plugin(setup)
        assert ASSISTANT_CATALOG.key in definition.required_capability_keys

    def test_layer_is_l4(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.layer == "L4"

    def test_kind_is_seam(self) -> None:
        from lca.contracts.protocols.declarative.declarative_common import PluginSpecKind

        definition = definition_from_plugin(setup)
        assert definition.spec.kind is PluginSpecKind.SEAM

    def test_effects_include_none_only(self) -> None:
        definition = definition_from_plugin(setup)
        assert EffectClass.NONE in definition.spec.effects
        assert EffectClass.FILESYSTEM not in definition.spec.effects
        assert EffectClass.MEMORY not in definition.spec.effects

    def test_test_suite_path_matches(self) -> None:
        definition = definition_from_plugin(setup)
        assert (
            definition.spec.verification.test_suite == "tests/plugins/assistant/test_bootstrap.py"
        )


# ── project_home_to_context_manifest 纯函数 ──────────────────────


class TestProjectHomeToContextManifest:
    def test_returns_context_manifest_with_five_items(
        self,
        assistant_a: Any,
    ) -> None:
        manifest = project_home_to_context_manifest(
            spec_home=Path(assistant_a.home_path),
            assistant_id=assistant_a.assistant_id,
        )
        assert isinstance(manifest, ContextManifest)
        assert len(manifest.items) == 5  # SOUL/IDENTITY/USER/AGENTS/goals

    def test_items_have_assistant_provenance(
        self,
        assistant_a: Any,
    ) -> None:
        manifest = project_home_to_context_manifest(
            spec_home=Path(assistant_a.home_path),
            assistant_id=assistant_a.assistant_id,
        )
        provenances = {item.provenance for item in manifest.items}
        assert all(p == f"assistant.bootstrap.{assistant_a.assistant_id}" for p in provenances)

    def test_bootstrap_items_carry_file_text(
        self,
        assistant_a: Any,
    ) -> None:
        manifest = project_home_to_context_manifest(
            spec_home=Path(assistant_a.home_path),
            assistant_id=assistant_a.assistant_id,
        )
        # AGENTS 文本 = tools.yaml / SOUL/IDENTITY/USER 各自文本
        names = sorted(item.payload.get("name") for item in manifest.items)
        assert names == ["AGENTS.md", "IDENTITY.md", "SOUL.md", "USER.md", "goals.yaml"]

    def test_goals_yaml_parsed(
        self,
        assistant_a: Any,
    ) -> None:
        manifest = project_home_to_context_manifest(
            spec_home=Path(assistant_a.home_path),
            assistant_id=assistant_a.assistant_id,
        )
        goals_item = next(
            item for item in manifest.items if item.payload.get("name") == "goals.yaml"
        )
        assert "goals" in goals_item.payload
        # default goals.yaml 模板 = ``goals: []`` + ``notes``;``goals`` 解析为 []
        # notes 是顶层额外字段,也透传(整 dict 形态);断言 goals 字段 = []
        assert goals_item.payload["goals"] == []

    def test_missing_config_face_raises(
        self,
        catalog: AssistantCatalogImpl,
        tmp_path: Path,
    ) -> None:
        # 模拟 home 缺 SOUL.md
        broken = tmp_path / "broken"
        broken.mkdir()
        (broken / "manifest.json").write_text(
            json.dumps({"schema_version": 1, "assistant_id": "x", "digests": {}}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="配置面缺失"):
            project_home_to_context_manifest(spec_home=broken, assistant_id="x")

    def test_agents_item_uses_workspace_instructions_kind(
        self,
        assistant_a: Any,
    ) -> None:
        manifest = project_home_to_context_manifest(
            spec_home=Path(assistant_a.home_path),
            assistant_id=assistant_a.assistant_id,
        )
        agents_item = next(
            item for item in manifest.items if item.payload.get("name") == "AGENTS.md"
        )
        assert agents_item.kind == "workspace_instructions"

    def test_soul_user_use_system_class(
        self,
        assistant_a: Any,
    ) -> None:
        from lca.contracts.models.core.perception import ContextClass

        manifest = project_home_to_context_manifest(
            spec_home=Path(assistant_a.home_path),
            assistant_id=assistant_a.assistant_id,
        )
        soul = next(item for item in manifest.items if item.payload.get("name") == "SOUL.md")
        user = next(item for item in manifest.items if item.payload.get("name") == "USER.md")
        assert soul.content_class == ContextClass.SYSTEM
        assert user.content_class == ContextClass.SYSTEM


# ── Memory layer exclusion(PR-4 新不变量 + I-A13)────────────────────


class TestMemoryLayerExcluded:
    def test_no_memory_string_in_manifest_items(
        self,
        assistant_a: Any,
    ) -> None:
        manifest = project_home_to_context_manifest(
            spec_home=Path(assistant_a.home_path),
            assistant_id=assistant_a.assistant_id,
        )
        for item in manifest.items:
            text_repr = str(item.payload) + item.provenance
            assert "MEMORY" not in text_repr, (
                f"item {item.payload.get('name')!r} 含 MEMORY 字面(I-A13):{text_repr[:80]}"
            )

    def test_bootstrap_propagates_memory_exclusion_check(
        self,
        bootstrap_service: BootstrapProjectionService,
        assistant_a: Any,
    ) -> None:
        projection = bootstrap_service.project(assistant_a.assistant_id)
        assert isinstance(projection, BootstrapProjection)
        # 即使将来 ``project_home_to_context_manifest`` 误引入 memory 字面,
        # bootstrap service 的内置 check 也会抛 ValueError
        for item in projection.manifest.items:
            assert "MEMORY" not in str(item.payload)


# ── Service.project(assistant_id) 集成路径 ──────────────────────────


class TestBootstrapProjectionService:
    def test_project_returns_bootstrap_projection(
        self,
        bootstrap_service: BootstrapProjectionService,
        assistant_a: Any,
    ) -> None:
        projection = bootstrap_service.project(assistant_a.assistant_id)
        assert projection.assistant_id == assistant_a.assistant_id
        assert isinstance(projection.manifest, ContextManifest)
        assert projection.items() == projection.manifest.items

    def test_project_unknown_assistant_raises(
        self,
        bootstrap_service: BootstrapProjectionService,
    ) -> None:
        with pytest.raises(AssistantCatalogError):
            bootstrap_service.project("asst_does_not_exist")

    def test_project_propagates_digest_mismatch(
        self,
        bootstrap_service: BootstrapProjectionService,
        assistant_a: Any,
        catalog: AssistantCatalogImpl,
    ) -> None:
        # 篡改 SOUL.md ⇒ catalog.get 抛 AssistantDigestMismatch ⇒ service 透传
        (Path(assistant_a.home_path) / "SOUL.md").write_text("tampered", encoding="utf-8")
        with pytest.raises(AssistantDigestMismatch):
            bootstrap_service.project(assistant_a.assistant_id)

    def test_project_after_reimport_succeeds(
        self,
        bootstrap_service: BootstrapProjectionService,
        assistant_a: Any,
    ) -> None:
        # 篡改 SOUL.md + 手动 patch manifest digest(模拟 reimport 效果)
        soul_path = Path(assistant_a.home_path) / "SOUL.md"
        soul_path.write_text("new SOUL content", encoding="utf-8")
        manifest_path = Path(assistant_a.home_path) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        from lca.plugins.assistant._home_layout import sha256_digest

        manifest["digests"]["SOUL.md"] = sha256_digest(soul_path)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        projection = bootstrap_service.project(assistant_a.assistant_id)
        assert projection.manifest is not None


# ── 跨助理投影隔离(PR-4 新不变量 + I-A6 类似)──────────────────────


class TestCrossAssistantProjectionIsolation:
    def test_assistant_a_soul_does_not_leak_into_b(
        self,
        bootstrap_service: BootstrapProjectionService,
        assistant_a: Any,
        assistant_b: Any,
    ) -> None:
        """助理 A 的 SOUL.md 文本不应出现在助理 B 的 ContextManifest。"""
        # 改写助理 A 的 SOUL.md 为独有特征字符串
        unique_marker = "ALICE_UNIQUE_SOUL_MARKER_XYZ"
        (Path(assistant_a.home_path) / "SOUL.md").write_text(unique_marker, encoding="utf-8")
        # 同步更新 A 的 manifest.digests 以便通过 catalog digest 校验
        manifest_path = Path(assistant_a.home_path) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        from lca.plugins.assistant._home_layout import sha256_digest

        manifest["digests"]["SOUL.md"] = sha256_digest(Path(assistant_a.home_path) / "SOUL.md")
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # A 投影应包含 marker,B 投影不应
        proj_a = bootstrap_service.project(assistant_a.assistant_id)
        proj_b = bootstrap_service.project(assistant_b.assistant_id)
        a_text = json.dumps(proj_a.manifest.items[0].payload, ensure_ascii=False)
        b_text = json.dumps(proj_b.manifest.items[0].payload, ensure_ascii=False)
        assert unique_marker in a_text
        assert unique_marker not in b_text

    def test_assistant_a_goals_does_not_leak_into_b(
        self,
        bootstrap_service: BootstrapProjectionService,
        assistant_a: Any,
        assistant_b: Any,
    ) -> None:
        unique_goal = "ASSISTANT_A_SPECIFIC_GOAL_42"
        goals_path_a = Path(assistant_a.home_path) / "goals.yaml"
        goals_path_a.write_text(
            f"goals:\n  - name: unique\n    description: {unique_goal}\n",
            encoding="utf-8",
        )
        # 同步更新 A 的 manifest.digests
        manifest_path = Path(assistant_a.home_path) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        from lca.plugins.assistant._home_layout import sha256_digest

        manifest["digests"]["goals.yaml"] = sha256_digest(goals_path_a)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        proj_a = bootstrap_service.project(assistant_a.assistant_id)
        proj_b = bootstrap_service.project(assistant_b.assistant_id)
        a_payload = json.dumps([item.payload for item in proj_a.manifest.items], ensure_ascii=False)
        b_payload = json.dumps([item.payload for item in proj_b.manifest.items], ensure_ascii=False)
        assert unique_goal in a_payload
        assert unique_goal not in b_payload


# ── 记忆面篡改不应触发 digest 失败(I-A13 双向)────────────────────


class TestMemoryTamperDoesNotAffectBootstrap:
    def test_memory_md_modification_does_not_break_projection(
        self,
        bootstrap_service: BootstrapProjectionService,
        assistant_a: Any,
    ) -> None:
        """记忆面写入不应导致 bootstrap 投影抛 AssistantDigestMismatch(I-A13 双向)。"""
        home = Path(assistant_a.home_path)
        (home / "MEMORY.md").write_text("some memory content", encoding="utf-8")
        (home / "memory" / "notes.json").write_text("{}", encoding="utf-8")
        projection = bootstrap_service.project(assistant_a.assistant_id)
        assert projection.manifest is not None
        # bootstrap items 不含 MEMORY 字面(隔离)
        for item in projection.manifest.items:
            assert "MEMORY.md" not in str(item.payload)
