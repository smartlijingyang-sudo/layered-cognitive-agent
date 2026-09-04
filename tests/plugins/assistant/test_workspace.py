"""assistant.workspace plugin tests(ADR-0187 §7 PR-4)。

覆盖契约:

- plugin Manifest:provides=assistant.workspace / requires=assistant.catalog /
  layer=L4 / kind=SEAM / effects=FILESYSTEM / test_suite 字符串对齐
- materialize_workspace_from_assistant(纯函数):
  * ExecutionSpace.space_id = "asstspace:<assistant_id>"
  * ExecutionSpace.workspace_path = "{home}/workspace/"
  * ExecutionSpace.backend = "local"
  * ExecutionSpace.acl_paths ⊆ workspace_path(I-A5)
  * 缺 workspace 子目录 ⇒ FileNotFoundError
- WorkspaceMaterializationService.materialize(assistant_id):
  * 返回 WorkspaceMaterialization
  * digest 不一致 ⇒ AssistantDigestMismatch 透传
  * 助理 home 缺失 ⇒ ValueError 透传
- 跨助理隔离:助理 A 的 workspace path 不出现在助理 B 的 ExecutionSpace
- ExecutionSpace 构造不变量:非绝对路径 / ACL 不在子树内 ⇒ ValueError
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lca.contracts.capabilities import ASSISTANT_CATALOG, ASSISTANT_WORKSPACE
from lca.contracts.models.act.execution_space import (
    ExecutionSpace,
    materialize_assistant_workspace,
)
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.harness.plugin_api import definition_from_plugin
from lca.harness.plugin_manifest import EffectClass
from lca.plugins.assistant.catalog import (
    AssistantCatalogError,
    AssistantCatalogImpl,
    AssistantDigestMismatch,
)
from lca.plugins.assistant.workspace import (
    WorkspaceMaterialization,
    WorkspaceMaterializationService,
    materialize_workspace_from_assistant,
    setup,
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
    return catalog.create(CreateAssistantRequest(name="Alice", description="first"))


@pytest.fixture
def assistant_b(catalog: AssistantCatalogImpl) -> Any:
    return catalog.create(CreateAssistantRequest(name="Bob", description="second"))


@pytest.fixture
def workspace_service(catalog: AssistantCatalogImpl) -> WorkspaceMaterializationService:
    return WorkspaceMaterializationService(catalog=catalog)


# ── Plugin Manifest ──────────────────────────────────────────────


class TestPluginManifest:
    def test_definition_id_namespace(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.id == "lca.plugins.assistant.workspace"

    def test_provides_assistant_workspace(self) -> None:
        definition = definition_from_plugin(setup)
        assert ASSISTANT_WORKSPACE.key in definition.provided_capability_keys

    def test_requires_assistant_catalog(self) -> None:
        definition = definition_from_plugin(setup)
        assert ASSISTANT_CATALOG.key in definition.required_capability_keys

    def test_layer_is_l4(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.layer == "L4"

    def test_kind_is_provider(self) -> None:
        """workspace plugin 有 FILESYSTEM effect ⇒ native spec 归 PROVIDER。

        PluginKind.SEAM 走 ``native_spec_from_declaration`` 时,若 effect
        列表含非 ``"none"`` 项会降级为 PROVIDER;workspace effect 含
        FILESYSTEM ⇒ 归 PROVIDER。
        """
        from lca.contracts.protocols.declarative.declarative_common import PluginSpecKind

        definition = definition_from_plugin(setup)
        assert definition.spec.kind is PluginSpecKind.PROVIDER

    def test_effects_include_filesystem(self) -> None:
        definition = definition_from_plugin(setup)
        assert EffectClass.FILESYSTEM in definition.spec.effects

    def test_test_suite_path_matches(self) -> None:
        definition = definition_from_plugin(setup)
        assert (
            definition.spec.verification.test_suite == "tests/plugins/assistant/test_workspace.py"
        )


# ── ExecutionSpace 构造不变量 ────────────────────────────────────


class TestExecutionSpaceInvariants:
    def test_relative_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="绝对路径"):
            ExecutionSpace(
                space_id="x",
                backend="local",
                workspace_path="relative/path",
            )

    def test_empty_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="非空"):
            ExecutionSpace(space_id="x", backend="local", workspace_path="  ")

    def test_acl_outside_workspace_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="workspace_path"):
            ExecutionSpace(
                space_id="x",
                backend="local",
                workspace_path=str(tmp_path),
                acl_paths=(str(tmp_path.parent),),  # 不在 workspace 子树
            )

    def test_acl_inside_workspace_accepted(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        sub = workspace / "subdir"
        sub.mkdir()
        space = ExecutionSpace(
            space_id="x",
            backend="local",
            workspace_path=str(workspace),
            acl_paths=(str(sub),),
        )
        assert str(sub) in space.acl_paths

    def test_materialize_assistant_workspace_space_id(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        workspace = home / "workspace"
        workspace.mkdir(parents=True)
        space = materialize_assistant_workspace(
            assistant_id="asst_abc123",
            home_path=str(home),
        )
        assert space.space_id == "asstspace:asst_abc123"
        assert space.backend == "local"
        assert space.workspace_path == str(workspace)
        assert space.workspace_path in space.acl_paths

    def test_parent_space_id_propagates(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        (home / "workspace").mkdir(parents=True)
        space = materialize_assistant_workspace(
            assistant_id="asst_x",
            home_path=str(home),
            parent_space_id="profile:web-assistant",
        )
        assert space.parent_space_id == "profile:web-assistant"


# ── materialize_workspace_from_assistant 纯函数 ──────────────────


class TestMaterializeWorkspace:
    def test_returns_execution_space(self, assistant_a: Any) -> None:
        space = materialize_workspace_from_assistant(
            assistant_id=assistant_a.assistant_id,
            home_path=assistant_a.home_path,
        )
        assert isinstance(space, ExecutionSpace)
        assert space.space_id == f"asstspace:{assistant_a.assistant_id}"

    def test_workspace_path_under_home(self, assistant_a: Any) -> None:
        space = materialize_workspace_from_assistant(
            assistant_id=assistant_a.assistant_id,
            home_path=assistant_a.home_path,
        )
        home = Path(assistant_a.home_path).resolve()
        assert Path(space.workspace_path).resolve().is_relative_to(home)
        assert space.workspace_path.endswith("workspace")

    def test_missing_workspace_subdir_raises(self, tmp_path: Path) -> None:
        # 模拟 home 但无 workspace/ 子目录
        home = tmp_path / "broken"
        home.mkdir()
        with pytest.raises(FileNotFoundError, match="workspace"):
            materialize_workspace_from_assistant(
                assistant_id="asst_broken",
                home_path=str(home),
            )


# ── Service.materialize 集成路径 ──────────────────────────────────


class TestWorkspaceMaterializationService:
    def test_materialize_returns_workspace_materialization(
        self, workspace_service: WorkspaceMaterializationService, assistant_a: Any
    ) -> None:
        result = workspace_service.materialize(assistant_a.assistant_id)
        assert isinstance(result, WorkspaceMaterialization)
        assert result.assistant_id == assistant_a.assistant_id
        assert result.space.space_id == f"asstspace:{assistant_a.assistant_id}"

    def test_materialize_unknown_assistant_raises(
        self, workspace_service: WorkspaceMaterializationService
    ) -> None:
        with pytest.raises(AssistantCatalogError):
            workspace_service.materialize("asst_does_not_exist")

    def test_materialize_propagates_digest_mismatch(
        self,
        workspace_service: WorkspaceMaterializationService,
        assistant_a: Any,
    ) -> None:
        # 篡改 SOUL.md ⇒ catalog.get 抛 AssistantDigestMismatch ⇒ service 透传
        (Path(assistant_a.home_path) / "SOUL.md").write_text("tampered", encoding="utf-8")
        with pytest.raises(AssistantDigestMismatch):
            workspace_service.materialize(assistant_a.assistant_id)

    def test_materialize_with_parent_space_id(
        self, workspace_service: WorkspaceMaterializationService, assistant_a: Any
    ) -> None:
        result = workspace_service.materialize(
            assistant_a.assistant_id, parent_space_id="profile:web-assistant"
        )
        assert result.space.parent_space_id == "profile:web-assistant"


# ── 跨助理 workspace 隔离(PR-4 新不变量 + I-A5 类似)────────────────


class TestCrossAssistantWorkspaceIsolation:
    def test_assistant_a_workspace_path_not_in_b(
        self,
        workspace_service: WorkspaceMaterializationService,
        assistant_a: Any,
        assistant_b: Any,
    ) -> None:
        """助理 A 的 workspace 绝对路径不应出现在助理 B 的 ExecutionSpace(I-A5)。"""
        a_result = workspace_service.materialize(assistant_a.assistant_id)
        b_result = workspace_service.materialize(assistant_b.assistant_id)
        assert a_result.space.workspace_path != b_result.space.workspace_path
        assert a_result.space.space_id != b_result.space.space_id
        # B 的 acl ⊆ B 的 workspace_path,绝不含 A 的 workspace_path
        assert a_result.space.workspace_path not in b_result.space.acl_paths
        # A 的 workspace_path 是绝对唯一,B 不可触达
        a_home = Path(assistant_a.home_path).resolve()
        b_workspace = Path(b_result.space.workspace_path).resolve()
        assert (
            not b_workspace.is_relative_to(a_home)
            or b_workspace == Path(a_result.space.workspace_path).resolve()
        )  # 只可能在 setup 同名时重合;此 fixture 中两个助理 home 不同

    def test_assistant_a_does_not_see_b_subtree(
        self,
        workspace_service: WorkspaceMaterializationService,
        assistant_a: Any,
        assistant_b: Any,
    ) -> None:
        """助理 A 的 ExecutionSpace.acl_paths 不应包含助理 B 的 home 子树(I-A5)。"""
        a_result = workspace_service.materialize(assistant_a.assistant_id)
        b_home = str(Path(assistant_b.home_path).resolve())
        for acl in a_result.space.acl_paths:
            assert not acl.startswith(b_home), f"助理 A 的 ACL {acl!r} 跨入助理 B 的 home 子树"
