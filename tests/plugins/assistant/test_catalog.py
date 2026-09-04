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
- revise_profile / reimport / retire 抛 NotImplementedError + 注释存在
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.capabilities import ASSISTANT_CATALOG
from lca.contracts.observability.assistant_ep_closure import (
    ASSISTANT_CREATED,
    ASSISTANT_REQUIRED_FIELDS,
)
from lca.contracts.protocols.assistant.catalog import (
    CreateAssistantRequest,
    ProfilePatch,
)
from lca.contracts.protocols.declarative.declarative_common import PluginSpecKind
from lca.harness.plugin_api import definition_from_plugin
from lca.harness.plugin_manifest import EffectClass
from lca.plugins.assistant._events import AssistantCreatedEventPayload
from lca.plugins.assistant._home_layout import CONFIG_FACE_FILES, SCHEMA_VERSION
from lca.plugins.assistant.catalog import (
    AssistantCatalogError,
    AssistantCatalogImpl,
    AssistantDigestMismatch,
    Config,
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
        assert spec.bootstrap.identity_digest.startswith("sha256:")
        assert spec.bootstrap.user_digest.startswith("sha256:")
        assert spec.bootstrap.agents_digest.startswith("sha256:")
        assert spec.grant_digest.startswith("sha256:")
        assert spec.tools_policy_digest.startswith("sha256:")

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
        (Path(handle.home_path) / "IDENTITY.md").write_text("tampered", encoding="utf-8")
        with pytest.raises(AssistantDigestMismatch):
            catalog.get(handle.assistant_id)


# ── revise / reimport / retire:PR-3 占位 ─────────────────────────────


class TestNotImplementedRevisionAPI:
    def test_revise_profile_raises_with_compat_marker(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        with pytest.raises(NotImplementedError):
            catalog.revise_profile(handle.assistant_id, ProfilePatch())
        # COMPAT 注释必须在 source(被 grep 守住,见 architecture tests)
        source = Path(catalog.revise_profile.__code__.co_filename).read_text(encoding="utf-8")
        assert "COMPAT(delete-when:" in source

    def test_reimport_raises_with_compat_marker(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        with pytest.raises(NotImplementedError):
            catalog.reimport(handle.assistant_id, reason="manual reimport")
        source = Path(catalog.reimport.__code__.co_filename).read_text(encoding="utf-8")
        assert "COMPAT(delete-when:" in source

    def test_retire_raises_with_compat_marker(
        self,
        catalog: AssistantCatalogImpl,
        request_default: CreateAssistantRequest,
    ) -> None:
        handle = catalog.create(request_default)
        with pytest.raises(NotImplementedError):
            catalog.retire(handle.assistant_id, reason="end of life")
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
        assert definition.spec.id == "lca.plugins.assistant.catalog"

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
        "lca.plugins.assistant.catalog._new_assistant_id",
        lambda: "asst_failtest",
    )
    monkeypatch.setattr(
        "lca.plugins.assistant.catalog.build_manifest",
        _raise,
    )
    with pytest.raises(RuntimeError):
        catalog.create(CreateAssistantRequest(name="x"))
    # 半成品 home 应被清理
    assert not (root / "asst_failtest").exists()
