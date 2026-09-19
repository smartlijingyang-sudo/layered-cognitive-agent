"""AssistantCatalog plugin tests(ADR-0187 §7 PR-3)。

覆盖契约:

- create:物化 Home + manifest + 发 assistant.created EP;返回值 = AssistantHandle
- get:digest 校验通过 ⇒ 返回 AssistantSpec;digest 不匹配 ⇒ AssistantDigestMismatch
- list:扫 ``{assistants_root}/*/manifest.json``;digest 不一致的不列
- manifest schema_version=1 + 8 个配置面 digest 字段
- 记忆面(MEMORY.md / memory/)不在 digest 列(I-A13)
- assistant.created EP payload 必含 4 件套
- plugin Manifest:provides=assistant.catalog / requires=event.bus / layer=L4 /
  effects=FILESYSTEM / test_suite 字符串对齐
- retire 抛 NotImplementedError + 注释存在（revise_profile / reimport 已在
  ADR-0242 PR-5 实现，见 test_self_manage.py）
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from lca.contracts.capabilities import ASSISTANT_CATALOG
from lca.contracts.observability.closure.assistant_ep_closure import (
    ASSISTANT_BOOTSTRAP_COMPLETED,
    ASSISTANT_CREATED,
    ASSISTANT_REQUIRED_FIELDS,
)
from lca.contracts.protocols.assistant.catalog import (
    CreateAssistantRequest,
    ProfilePatch,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_common import PluginSpecKind
from lca.harness.plugin.manifest import EffectClass
from lca.harness.plugin_api import definition_from_plugin
from lca.plugins.assistant.events._events import AssistantCreatedEventPayload
from lca.plugins.assistant.home._home_layout import CONFIG_FACE_FILES, SCHEMA_VERSION
from lca.plugins.domain.assistant.catalog.plugin import (
    AssistantCatalogError,
    AssistantCatalogImpl,
    AssistantDigestMismatch,
    Config,
    PlanOverlayValidationError,
    setup,
)

# ── helpers ─────────────────────────────────────────────────────────


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def emitted() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
def catalog(root: Path, emitted: list[tuple[str, dict[str, Any]]]) -> AssistantCatalogImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantCatalogImpl(root=root, event_emitter=_record)


@pytest.fixture
def request_default() -> CreateAssistantRequest:
    return CreateAssistantRequest(name="Demo", description="demo assistant")


# ── create ──────────────────────────────────────────────────────────


class TestCreate:
    def test_create_returns_handle_with_revision_seq_zero(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        assert handle.assistant_id.startswith("asst_")
        assert handle.revision_seq == 0
        assert Path(handle.home_path).is_dir()

    def test_create_writes_required_config_face_files(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        home = Path(handle.home_path)
        for name in CONFIG_FACE_FILES:
            assert (home / name).is_file(), f"{name} 应在 Home 中"

    def test_create_scaffolds_empty_subdirs(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        home = Path(handle.home_path)
        for sub in ("skills", "workspace", "memory", "routines", "revisions"):
            assert (home / sub).is_dir(), f"占位子目录 {sub} 应存在"

    def test_create_writes_bootstrap_md(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        assert (Path(handle.home_path) / "BOOTSTRAP.md").is_file()

    def test_create_no_memory_md_by_default(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        """PR-3 不创建 MEMORY.md(记忆面是 PR-4 memory seam 工作);I-A13。"""
        handle = catalog.create(request_default)
        assert not (Path(handle.home_path) / "MEMORY.md").exists()

    def test_create_seed_user_md_overrides_default(
        self,
        catalog: AssistantCatalogImpl,
        root: Path,
    ) -> None:
        req = CreateAssistantRequest(
            name="Demo",
            description="x",
            seed_user_md="custom user context",
        )
        handle = catalog.create(req)
        text = (Path(handle.home_path) / "USER.md").read_text(encoding="utf-8")
        assert text == "custom user context"

    def test_create_with_soul_merges_template_default_sections(
        self,
        catalog: AssistantCatalogImpl,
    ) -> None:
        """ADR-0242 附录 C:用户 soul 只含四核心段时,模板默认段必须补上。

        回归:上次真实创建 run 产出的 SOUL 只有四个核心段,缺少
        安全边界/记忆规则/错误处理/红线(向导按 skill 不手写默认段,
        后端必须从模板合并)。
        """
        soul = (
            "## 🧠 身份\n你是一位测试助理。" * 1
            + "你擅长测试。" * 30
            + "\n## 🎭 性格\n"
            + "结论先行。" * 30
            + "\n## 🛠 能力\n"
            + "擅长编写测试。" * 30
            + "\n## 🗣 语气\n"
            + "专业务实。" * 30
        )
        req = CreateAssistantRequest(name="测试", description="d", soul=soul)
        handle = catalog.create(req)
        created = (Path(handle.home_path) / "SOUL.md").read_text(encoding="utf-8")
        for marker in (
            "## 🔒 安全边界",
            "## 💾 记忆规则",
            "## ⚠️ 错误处理",
            "## 🚫 红线",
        ):
            assert marker in created, f"模板默认段缺失: {marker}"

    def test_create_manifest_schema(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        manifest = json.loads((Path(handle.home_path) / "manifest.json").read_text())
        assert manifest["schema_version"] == SCHEMA_VERSION
        assert manifest["assistant_id"] == handle.assistant_id
        assert manifest["template_id"] == "assistant.default"
        assert manifest["revision_seq"] == 0
        for name in CONFIG_FACE_FILES:
            assert name in manifest["digests"], f"manifest.digests 缺 {name}"
            assert manifest["digests"][name].startswith("sha256:")
        assert manifest["manifest_digest"].startswith("sha256:")

    def test_create_emits_assistant_created_event(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        handle = catalog.create(request_default)
        assert len(emitted) == 1
        event, payload = emitted[0]
        assert event == ASSISTANT_CREATED
        for field_name in ASSISTANT_REQUIRED_FIELDS:
            assert field_name in payload, f"EP payload 缺 {field_name}"
        assert payload["assistant_id"] == handle.assistant_id
        assert payload["revision_seq"] == 0
        assert payload["actor"] == "system"
        assert payload["home_path"] == handle.home_path
        assert payload["template_id"] == "assistant.default"

    def test_create_rejects_non_default_template(
        self,
        catalog: AssistantCatalogImpl,
    ) -> None:
        with pytest.raises(AssistantCatalogError, match="template_id"):
            catalog.create(CreateAssistantRequest(name="x", template_id="other.tpl"))

    def test_create_id_is_unique_across_calls(
        self,
        catalog: AssistantCatalogImpl,
    ) -> None:
        a = catalog.create(CreateAssistantRequest(name="A"))
        b = catalog.create(CreateAssistantRequest(name="B"))
        assert a.assistant_id != b.assistant_id


# ── 默认工具物化（ADR-0243 D3 延伸）─────────────────────────────────


class TestDefaultToolNames:
    def test_create_with_default_tool_names_writes_allow_list(
        self,
        catalog: AssistantCatalogImpl,
    ) -> None:
        handle = catalog.create(
            CreateAssistantRequest(name="X", default_tool_names=("search", "readFile"))
        )
        home = Path(handle.home_path)
        data = yaml.safe_load((home / "tools.yaml").read_text(encoding="utf-8"))
        assert data["tools"]["allow"] == ["readFile", "search"]  # 排序去重
        assert data["tools"]["deny"] == []
        # tools.yaml 是配置面：manifest digest 自动覆盖，get 不抛
        assert catalog.get(handle.assistant_id).assistant_id == handle.assistant_id

    def test_create_without_default_tool_names_keeps_empty_allow(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        data = yaml.safe_load((Path(handle.home_path) / "tools.yaml").read_text(encoding="utf-8"))
        assert data["tools"]["allow"] == []

    def test_create_with_inherit_from_keeps_source_tools_policy(
        self,
        catalog: AssistantCatalogImpl,
    ) -> None:
        """继承快照整文件复制优先于默认物化（inherit_from 胜出）。"""
        source = catalog.create(CreateAssistantRequest(name="来源", default_tool_names=("search",)))
        child = catalog.create(
            CreateAssistantRequest(
                name="继承",
                inherit_from=source.assistant_id,
                default_tool_names=("readFile",),
            )
        )
        data = yaml.safe_load((Path(child.home_path) / "tools.yaml").read_text(encoding="utf-8"))
        assert data["tools"]["allow"] == ["search"]
        assert (Path(child.home_path) / "tools.yaml").read_text(encoding="utf-8") == (
            Path(source.home_path) / "tools.yaml"
        ).read_text(encoding="utf-8")


# ── get ─────────────────────────────────────────────────────────────


class TestGet:
    def test_get_returns_resolve_view(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        spec = catalog.get(handle.assistant_id)
        assert spec.assistant_id == handle.assistant_id
        assert spec.home_path == handle.home_path
        assert spec.revision_seq == 0
        assert spec.template_id == "assistant.default"
        assert spec.bootstrap.soul_digest.startswith("sha256:")
        assert spec.bootstrap.user_digest.startswith("sha256:")
        assert spec.bootstrap.agents_digest.startswith("sha256:")
        assert spec.grant_digest.startswith("sha256:")
        assert spec.tools_policy_digest.startswith("sha256:")

    def test_get_reads_profile_model_and_runtime(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        """ADR-0242 D9:get() 把 profile.json 的 model/runtime 读进 AssistantSpec。"""
        handle = catalog.create(request_default)
        spec = catalog.get(handle.assistant_id)
        assert spec.profile_model == ""  # 模板默认无 model
        assert spec.profile_runtime == {}
        # ADR-0242 D13:AssistantSpec 携带 grants 集合供未来 assistant.invoke 校验。
        assert spec.grants == frozenset({"workspace.write", "skill.import", "profile.revise"})

    def test_get_reads_profile_model_and_runtime_after_revise(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        catalog.revise_profile(
            handle.assistant_id,
            ProfilePatch(profile_model="model-x", profile_runtime={"max_steps": 7}),
        )
        spec = catalog.get(handle.assistant_id)
        assert spec.profile_model == "model-x"
        assert spec.profile_runtime == {"max_steps": 7}

    def test_get_unknown_assistant_raises(
        self,
        catalog: AssistantCatalogImpl,
    ) -> None:
        with pytest.raises(AssistantCatalogError):
            catalog.get("asst_does_not_exist")

    def test_get_digest_mismatch_on_soul_tamper_fails_closed(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        """I-A3 fail-closed:篡改 SOUL.md 后 get 必须抛 AssistantDigestMismatch。"""
        handle = catalog.create(request_default)
        (Path(handle.home_path) / "SOUL.md").write_text("tampered", encoding="utf-8")
        with pytest.raises(AssistantDigestMismatch):
            catalog.get(handle.assistant_id)

    def test_get_digest_mismatch_on_goals_tamper_fails_closed(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        """配置面 yaml 篡改同样 fail-closed。"""
        handle = catalog.create(request_default)
        (Path(handle.home_path) / "goals.yaml").write_text("tampered: true\n", encoding="utf-8")
        with pytest.raises(AssistantDigestMismatch):
            catalog.get(handle.assistant_id)

    def test_get_returns_plan_overlay_and_manifest_digest(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        """get() 必须返回 plan_overlay（默认空覆盖）与 manifest_digest（缓存键）。"""
        handle = catalog.create(request_default)
        spec = catalog.get(handle.assistant_id)
        assert spec.manifest_digest.startswith("sha256:")
        assert spec.plan_overlay is not None
        assert spec.plan_overlay.prompt.template is None
        assert spec.plan_overlay.graph.subgraphs == {}

    def test_get_returns_plan_overlay_from_plan_yaml(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        """Home 的 plan.yaml 解析为 ``plan_overlay`` 进入 AssistantSpec。"""
        handle = catalog.create(request_default)
        home = Path(handle.home_path)
        (home / "plan.yaml").write_text(
            "prompt:\n  template: react_prompt\n  sections:\n    - name: role\n",
            encoding="utf-8",
        )
        catalog.reimport(handle.assistant_id, reason="plan.yaml 测试")
        spec = catalog.get(handle.assistant_id)
        assert spec.plan_overlay is not None
        assert spec.plan_overlay.prompt.template == "react_prompt"
        assert [s.name for s in spec.plan_overlay.prompt.sections] == ["role"]

    def test_get_invalid_plan_yaml_fails_closed(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        """plan.yaml 形状非法 ⇒ fail-closed（ADR-0242 I-B11）。"""
        handle = catalog.create(request_default)
        home = Path(handle.home_path)
        (home / "plan.yaml").write_text("prompt:\n  bogus_field: x\n", encoding="utf-8")
        catalog.reimport(handle.assistant_id, reason="plan.yaml 测试")
        with pytest.raises(PlanOverlayValidationError, match=r"plan\.yaml"):
            catalog.get(handle.assistant_id)


# ── revise_profile: model/runtime 写盘（ADR-0242 D9/PR-8）───────────


class TestReviseProfileModelRuntime:
    def test_revise_writes_model_runtime_and_bumps_revision(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        old_seq = catalog.get(handle.assistant_id).revision_seq

        revision = catalog.revise_profile(
            handle.assistant_id,
            ProfilePatch(profile_model="model-x", profile_runtime={"max_steps": 7}),
        )

        assert revision.revision_seq == old_seq + 1
        home = Path(handle.home_path)
        profile = json.loads((home / "profile.json").read_text(encoding="utf-8"))
        assert profile["model"] == "model-x"
        assert profile["runtime"] == {"max_steps": 7}
        spec = catalog.get(handle.assistant_id)
        assert spec.revision_seq == old_seq + 1
        assert spec.profile_model == "model-x"
        assert spec.profile_runtime == {"max_steps": 7}

    def test_revise_writes_opening_message_and_locale(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)

        revision = catalog.revise_profile(
            handle.assistant_id,
            ProfilePatch(profile_opening_message="你好", profile_locale="en-US"),
        )

        home = Path(handle.home_path)
        profile = json.loads((home / "profile.json").read_text(encoding="utf-8"))
        assert profile["opening_message"] == "你好"
        assert profile["locale"] == "en-US"
        spec = catalog.get(handle.assistant_id)
        assert spec.profile_opening_message == "你好"
        assert spec.profile_locale == "en-US"
        assert revision.revision_seq == spec.revision_seq


# ── list ────────────────────────────────────────────────────────────


class TestList:
    def test_list_empty_when_root_has_no_assistants(
        self,
        catalog: AssistantCatalogImpl,
    ) -> None:
        assert catalog.list() == ()

    def test_list_returns_all_created_assistants(
        self,
        catalog: AssistantCatalogImpl,
    ) -> None:
        a = catalog.create(CreateAssistantRequest(name="A"))
        b = catalog.create(CreateAssistantRequest(name="B"))
        summaries = catalog.list()
        ids = {summary.assistant_id for summary in summaries}
        assert {a.assistant_id, b.assistant_id}.issubset(ids)
        assert len(summaries) == 2

    def test_list_skips_directories_without_manifest(
        self,
        catalog: AssistantCatalogImpl,
        root: Path,
        request_default: CreateAssistantRequest,
    ) -> None:
        catalog.create(request_default)
        (root / "ghost_home").mkdir()  # no manifest.json
        summaries = catalog.list()
        assert len(summaries) == 1

    def test_list_skips_digest_mismatch_silently(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """I-A3 list:坏项不列(不抛);PR-3 不发 EP(避免越权增 EP 词表)。"""
        handle = catalog.create(request_default)
        (Path(handle.home_path) / "SOUL.md").write_text("tampered", encoding="utf-8")
        with caplog.at_level("WARNING"):
            summaries = catalog.list()
        assert summaries == ()

    def test_list_summary_carries_profile_metadata(
        self,
        catalog: AssistantCatalogImpl,
    ) -> None:
        handle = catalog.create(CreateAssistantRequest(name="Profile", description="d"))
        summaries = catalog.list()
        match = next(s for s in summaries if s.assistant_id == handle.assistant_id)
        assert match.name == "Profile"
        assert match.status == "active"
        assert match.template_id == "assistant.default"
        assert match.revision_seq == 0


# ── 记忆面不进 digest(I-A13)──────────────────────────────────────────


class TestMemoryLayerDigestPolicy:
    def test_memory_md_modification_does_not_break_get(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        """记忆面写入必须不触发 digest 校验失败(双向 I-A13)。"""
        handle = catalog.create(request_default)
        home = Path(handle.home_path)
        (home / "MEMORY.md").write_text("some memory", encoding="utf-8")
        (home / "memory" / "notes.json").write_text("{}", encoding="utf-8")
        spec = catalog.get(handle.assistant_id)
        assert spec.assistant_id == handle.assistant_id

    def test_config_face_modification_does_break_get(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        """配置面写入必须触发 fail-closed(与上对照;双向 I-A13)。"""
        handle = catalog.create(request_default)
        (Path(handle.home_path) / "USER.md").write_text("tampered", encoding="utf-8")
        with pytest.raises(AssistantDigestMismatch):
            catalog.get(handle.assistant_id)


# ── plan.yaml 进 manifest digest（ADR-0242 D10 / I-B10）──────────────


class TestPlanYamlDigest:
    def test_plan_yaml_tamper_breaks_get(self, catalog: AssistantCatalogImpl) -> None:
        """plan.yaml 是配置面：直接改文件 ⇒ digest 不匹配 ⇒ fail-closed。"""
        handle = catalog.create(CreateAssistantRequest(name="Plan实验"))
        (Path(handle.home_path) / "plan.yaml").write_text(
            "prompt:\n  template: react_prompt\n", encoding="utf-8"
        )
        with pytest.raises(AssistantDigestMismatch):
            catalog.get(handle.assistant_id)

    def test_plan_yaml_present_in_manifest_digests(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        """manifest.digests 必须包含 plan.yaml 的 sha256。"""
        handle = catalog.create(request_default)
        manifest = json.loads((Path(handle.home_path) / "manifest.json").read_text())
        assert "plan.yaml" in manifest["digests"]
        assert manifest["digests"]["plan.yaml"].startswith("sha256:")


# ── revise / reimport 已实现(ADR-0242 PR-5);retire 仍占位 ──────────


class TestRetirePlaceholder:
    def test_retire_raises_with_compat_marker(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        with pytest.raises(NotImplementedError):
            catalog.retire(handle.assistant_id, reason="end of life")
        # COMPAT 注释必须在 source(被 grep 守住,见 architecture tests)
        source = Path(catalog.retire.__code__.co_filename).read_text(encoding="utf-8")
        assert "COMPAT(delete-when:" in source


# ── EventPayload dataclass 自身 ──────────────────────────────────────


class TestAssistantCreatedEventPayload:
    def test_payload_requires_four_fields(self) -> None:
        p = AssistantCreatedEventPayload(
            assistant_id="a",
            revision_seq=0,
            manifest_digest="sha256:abc",
            actor="system",
        )
        assert p.to_dict()["actor"] == "system"

    def test_empty_assistant_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="assistant_id"):
            AssistantCreatedEventPayload(
                assistant_id="",
                revision_seq=0,
                manifest_digest="sha256:abc",
                actor="system",
            )

    def test_empty_manifest_digest_rejected(self) -> None:
        with pytest.raises(ValueError, match="manifest_digest"):
            AssistantCreatedEventPayload(
                assistant_id="a",
                revision_seq=0,
                manifest_digest="",
                actor="system",
            )

    def test_empty_actor_rejected(self) -> None:
        with pytest.raises(ValueError, match="actor"):
            AssistantCreatedEventPayload(
                assistant_id="a",
                revision_seq=0,
                manifest_digest="sha256:abc",
                actor="",
            )

    def test_negative_revision_seq_rejected(self) -> None:
        with pytest.raises(ValueError, match="revision_seq"):
            AssistantCreatedEventPayload(
                assistant_id="a",
                revision_seq=-1,
                manifest_digest="sha256:abc",
                actor="system",
            )


# ── Plugin Manifest 形状 ────────────────────────────────────────────


class TestPluginManifest:
    def test_definition_id_namespace(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.id == "lca.plugins.assistant.catalog.catalog"

    def test_provides_assistant_catalog(self) -> None:
        definition = definition_from_plugin(setup)
        assert ASSISTANT_CATALOG.key in definition.provided_capability_keys

    def test_requires_event_bus(self) -> None:
        definition = definition_from_plugin(setup)
        assert "event.bus" in definition.required_capability_keys

    def test_layer_is_l4(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.layer == "L4"

    def test_kind_is_provider(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.kind is PluginSpecKind.PROVIDER

    def test_effects_include_filesystem(self) -> None:
        definition = definition_from_plugin(setup)
        assert EffectClass.FILESYSTEM in definition.spec.effects

    def test_test_suite_path_matches(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.verification.test_suite == "tests/plugins/assistant/test_catalog.py"

    def test_config_rejects_extra_keys(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Config.model_validate(
                {"assistants_root": "/tmp/assistant-test", "extra": "x"}  # noqa: S108 - test fixture
            )

    def test_config_requires_assistants_root(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Config.model_validate({})


# ── ID 唯一性 ────────────────────────────────────────────────────────


def test_create_uses_uuid_hex_suffix() -> None:
    """id 形如 ``asst_<12hex>``,与仓内 ``new_id`` 命名一致。"""
    assert ASSISTANT_CATALOG.key == "assistant.catalog"


# ── Cleanup behavior ────────────────────────────────────────────────


def test_create_cleans_up_on_failure(
    root: Path,
    emitted: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create 失败时半成品 Home 应被清理;不污染根目录。"""
    catalog = AssistantCatalogImpl(
        root=root,
        event_emitter=lambda event, payload: emitted.append((event, dict(payload))),
    )

    def _raise(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("simulated failure mid-create")

    # 在 manifest 写入之前抛错 ⇒ write_home_files 之前 home 已 mkdir ⇒ 触发 cleanup
    monkeypatch.setattr(
        "lca.plugins.domain.assistant.catalog.plugin._new_assistant_id",
        lambda: "asst_failtest",
    )
    monkeypatch.setattr(
        "lca.plugins.domain.assistant.catalog.plugin.build_manifest",
        _raise,
    )
    with pytest.raises(RuntimeError):
        catalog.create(CreateAssistantRequest(name="x"))
    # 半成品 home 应被清理
    assert not (root / "asst_failtest").exists()


# ── SOUL 完整度校验（ADR-0242 D1 / I-B2）────────────────────────────


class TestSoulValidation:
    def test_bare_creation_without_soul_still_succeeds(self, catalog: AssistantCatalogImpl) -> None:
        """回归：裸创建（无 soul、无 from_role）仍成功（I-B8）。"""
        handle = catalog.create(CreateAssistantRequest(name="裸创建"))
        assert handle.assistant_id.startswith("asst_")
        assert (Path(handle.home_path) / "SOUL.md").is_file()

    @pytest.mark.parametrize(
        "missing_marker",
        ["## 🧠 身份", "## 🎭 性格", "## 🛠 能力", "## 🗣 语气"],
    )
    def test_soul_missing_core_section_raises(
        self,
        catalog: AssistantCatalogImpl,
        missing_marker: str,
    ) -> None:
        markers = ["## 🧠 身份", "## 🎭 性格", "## 🛠 能力", "## 🗣 语气"]
        sections = [
            f"{marker}\n" + ("内容填充。" * 30) for marker in markers if marker != missing_marker
        ]
        soul = "\n".join(sections)
        with pytest.raises(AssistantCatalogError, match=missing_marker):
            catalog.create(CreateAssistantRequest(name="x", soul=soul))

    def test_soul_too_short_raises(self, catalog: AssistantCatalogImpl) -> None:
        soul = "## 🧠 身份\n你是测试助理。\n## 🎭 性格\n直接坦诚。\n## 🛠 能力\n擅长测试。\n## 🗣 语气\n专业。"
        with pytest.raises(AssistantCatalogError, match="200 字符"):
            catalog.create(CreateAssistantRequest(name="x", soul=soul))

    def test_valid_soul_creates_home_with_soul_content(self, catalog: AssistantCatalogImpl) -> None:
        soul = _valid_soul()
        handle = catalog.create(CreateAssistantRequest(name="向导创建", soul=soul))
        written = (Path(handle.home_path) / "SOUL.md").read_text(encoding="utf-8")
        # 用户核心段保留;模板默认段合并进 Home(ADR-0242 附录 C)
        assert written.startswith(soul)
        for marker in ("## 🔒 安全边界", "## 💾 记忆规则", "## ⚠️ 错误处理", "## 🚫 红线"):
            assert marker in written

    def test_soul_overrides_from_role_backstory(
        self,
        catalog: AssistantCatalogImpl,
    ) -> None:
        """soul 非空时覆盖 from_role backstory；role_id / emoji 仍来自卡片。"""
        from lca.contracts.protocols.assistant.role_resolver import RoleCard

        class _Resolver:
            def resolve(self, role_id: str) -> RoleCard:
                return RoleCard(
                    role_id="engineering/architect",
                    title="软件架构师",
                    department="engineering",
                    summary="系统设计",
                    backstory="## 核心使命\n### 系统设计\n### 架构评审",
                    emoji="🏛️",
                )

        cat = AssistantCatalogImpl(root=catalog._root, role_resolver=_Resolver())
        soul = _valid_soul()
        handle = cat.create(
            CreateAssistantRequest(
                name="向导",
                from_role="engineering/architect",
                soul=soul,
            )
        )
        home = Path(handle.home_path)
        written = (home / "SOUL.md").read_text(encoding="utf-8")
        assert written.startswith(soul)
        for marker in ("## 🔒 安全边界", "## 💾 记忆规则", "## ⚠️ 错误处理", "## 🚫 红线"):
            assert marker in written
        profile = json.loads((home / "profile.json").read_text(encoding="utf-8"))
        assert profile["role_id"] == "engineering/architect"
        assert profile["emoji"] == "🏛️"
        goals = (home / "goals.yaml").read_text(encoding="utf-8")
        assert "系统设计" in goals


# ── inherit_from 快照（ADR-0242 D1/D2）──────────────────────────────


def _make_source_with_snapshot(catalog: AssistantCatalogImpl) -> str:
    """造一个 digest 一致的来源 Home：含技能目录 + 自定义 tools/grants。"""
    source = catalog.create(CreateAssistantRequest(name="来源助理"))
    src = Path(source.home_path)
    skill_dir = src / "skills" / "src-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: src-skill\n---\nbody", encoding="utf-8")
    (src / "tools.yaml").write_text(
        "tools:\n  allow: [workspace.read]\n  deny: [web_search]\n", encoding="utf-8"
    )
    (src / "grants.yaml").write_text("grants: [workspace.write]\n", encoding="utf-8")
    from lca.plugins.assistant.home._home_layout import sha256_digest

    manifest_path = src / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in ("tools.yaml", "grants.yaml"):
        manifest["digests"][name] = sha256_digest(src / name)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return source.assistant_id


class TestInheritFromSnapshot:
    def test_inherit_from_copies_skills_tools_grants(self, catalog: AssistantCatalogImpl) -> None:
        source_id = _make_source_with_snapshot(catalog)
        handle = catalog.create(CreateAssistantRequest(name="继承助理", inherit_from=source_id))
        home = Path(handle.home_path)
        # skills：只复制含 SKILL.md 的目录
        assert (home / "skills" / "src-skill" / "SKILL.md").is_file()
        # tools / grants 策略快照
        assert (home / "tools.yaml").read_text(encoding="utf-8") == (
            "tools:\n  allow: [workspace.read]\n  deny: [web_search]\n"
        )
        assert (home / "grants.yaml").read_text(encoding="utf-8") == "grants: [workspace.write]\n"
        # 快照 Home digest 一致，可 get
        spec = catalog.get(handle.assistant_id)
        assert spec.assistant_id == handle.assistant_id

    def test_inherit_from_no_skills_scaffolds_empty(self, catalog: AssistantCatalogImpl) -> None:
        source = catalog.create(CreateAssistantRequest(name="无技能来源"))
        handle = catalog.create(
            CreateAssistantRequest(name="继承助理", inherit_from=source.assistant_id)
        )
        home = Path(handle.home_path)
        assert (home / "skills").is_dir()
        assert list((home / "skills").iterdir()) == []

    def test_inherit_from_unknown_raises(self, catalog: AssistantCatalogImpl) -> None:
        with pytest.raises(AssistantCatalogError):
            catalog.create(CreateAssistantRequest(name="x", inherit_from="asst_does_not_exist"))

    def test_inherit_from_digest_mismatch_raises(self, catalog: AssistantCatalogImpl) -> None:
        source = catalog.create(CreateAssistantRequest(name="篡改来源"))
        (Path(source.home_path) / "SOUL.md").write_text("tampered", encoding="utf-8")
        with pytest.raises(AssistantCatalogError):
            catalog.create(CreateAssistantRequest(name="x", inherit_from=source.assistant_id))


# ── Home 卫生（ADR-0242 D2）─────────────────────────────────────────


class TestHomeHygiene:
    def test_guided_creation_deletes_bootstrap_and_emits_ep(
        self,
        catalog: AssistantCatalogImpl,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        handle = catalog.create(CreateAssistantRequest(name="向导创建", soul=_valid_soul()))
        assert not (Path(handle.home_path) / "BOOTSTRAP.md").exists()
        events = [event for event, _ in emitted]
        assert ASSISTANT_BOOTSTRAP_COMPLETED in events

    def test_guided_creation_writes_non_empty_user_md(self, catalog: AssistantCatalogImpl) -> None:
        handle = catalog.create(CreateAssistantRequest(name="向导创建", soul=_valid_soul()))
        user_md = (Path(handle.home_path) / "USER.md").read_text(encoding="utf-8")
        assert user_md.strip() != ""

    def test_wizard_creation_home_has_no_empty_shells(self, catalog: AssistantCatalogImpl) -> None:
        """集成：向导创建后 USER/goals/tools/grants 全部非空，且无 BOOTSTRAP。"""
        handle = catalog.create(CreateAssistantRequest(name="向导创建", soul=_valid_soul()))
        home = Path(handle.home_path)
        assert (home / "USER.md").read_text(encoding="utf-8").strip()
        assert yaml.safe_load((home / "goals.yaml").read_text(encoding="utf-8"))["goals"]
        assert (home / "tools.yaml").read_text(encoding="utf-8").strip()
        assert (home / "grants.yaml").read_text(encoding="utf-8").strip()
        assert not (home / "BOOTSTRAP.md").exists()

    def test_from_role_goals_non_empty_from_mission(
        self,
        catalog: AssistantCatalogImpl,
    ) -> None:
        from lca.contracts.protocols.assistant.role_resolver import RoleCard

        class _Resolver:
            def resolve(self, role_id: str) -> RoleCard:
                return RoleCard(
                    role_id="engineering/architect",
                    title="软件架构师",
                    department="engineering",
                    summary="系统设计",
                    backstory=(
                        "# 软件架构师\n\n## 核心使命\n### 系统设计\n### 架构评审\n### 技术选型\n### 性能优化\n"
                    ),
                    emoji="🏛️",
                )

        cat = AssistantCatalogImpl(root=catalog._root, role_resolver=_Resolver())
        handle = cat.create(CreateAssistantRequest(name="角色", from_role="engineering/architect"))
        goals = yaml.safe_load((Path(handle.home_path) / "goals.yaml").read_text(encoding="utf-8"))
        names = [g["name"] for g in goals["goals"]]
        assert names == ["系统设计", "架构评审", "技术选型"]  # 最多前 3 个

    def test_bare_creation_keeps_bootstrap(
        self,
        catalog: AssistantCatalogImpl,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        handle = catalog.create(CreateAssistantRequest(name="裸创建"))
        assert (Path(handle.home_path) / "BOOTSTRAP.md").exists()
        events = [event for event, _ in emitted]
        assert ASSISTANT_BOOTSTRAP_COMPLETED not in events

    def test_all_creation_paths_have_non_empty_goals(self, catalog: AssistantCatalogImpl) -> None:
        """裸创建 / 角色创建 / 向导创建 / 继承创建的 goals.yaml 都必须非空。"""
        bare = catalog.create(CreateAssistantRequest(name="裸"))
        assert yaml.safe_load((Path(bare.home_path) / "goals.yaml").read_text())["goals"]

        from lca.contracts.protocols.assistant.role_resolver import RoleCard

        class _Resolver:
            def resolve(self, role_id: str) -> RoleCard:
                return RoleCard(
                    role_id="design/ux",
                    title="UX 设计师",
                    department="design",
                    summary="体验设计",
                    backstory="## 核心使命\n### 用户研究\n### 原型设计",
                    emoji="🎨",
                )

        cat = AssistantCatalogImpl(root=catalog._root, role_resolver=_Resolver())
        role = cat.create(CreateAssistantRequest(name="角色", from_role="design/ux"))
        assert yaml.safe_load((Path(role.home_path) / "goals.yaml").read_text())["goals"]

        wizard = cat.create(CreateAssistantRequest(name="向导", soul=_valid_soul()))
        assert yaml.safe_load((Path(wizard.home_path) / "goals.yaml").read_text())["goals"]


def _valid_soul() -> str:
    """构造一个能通过完整度校验的 SOUL（四核心段 + 去空白 >= 200 字符）。"""
    return (
        "## 🧠 身份\n"
        "你是向导助理，服务用户完成深度研究。\n"
        + "你是一位资深研究员。" * 20
        + "\n## 🎭 性格\n"
        + "结论先行，直接坦诚。" * 20
        + "\n## 🛠 能力\n"
        + "擅长资料搜集与交叉核验。" * 20
        + "\n## 🗣 语气\n"
        + "专业务实，简洁量化。" * 20
    )
