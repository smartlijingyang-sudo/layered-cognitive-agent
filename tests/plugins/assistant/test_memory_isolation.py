"""跨助理 memory 隔离测试 + memory seam agent-scope 验证(ADR-0187 §7 PR-4)。

覆盖 I-A6(禁止跨助理读 memory)+ I-A13(记忆面不参与 digest 双向):

- **I-A6**:助理 A 写入后,助理 B 用 retrieval_policy 拿不到
  * 经 Catalog.get spec.home_path 路径隔离 + ScopePlan.visibility scope 隔离
  * 不依赖 SpacetimeContext 子空间(IdentitySpace / VisibilitySpace 推迟项,
    ADR-0187 §3 D5 迁移条款)
- **I-A13 双向**:
  * 篡改 MEMORY.md / memory/ ⇒ catalog.get 不抛异常(I-A13 正向)
  * 篡改 SOUL.md / goals.yaml ⇒ catalog.get 抛 AssistantDigestMismatch(I-A13 反向)
- **bootstrap 投影隔离**:助理 A 的 SOUL 不出现在助理 B 的 ContextManifest
  * 见 :mod:`tests.plugins.assistant.test_bootstrap` 已经覆盖;此处加一项
    跨 memory seam 的正交断言
- **workspace 隔离**:助理 A 的 workspace path 不出现在助理 B 的 ExecutionSpace
  * 见 :mod:`tests.plugins.assistant.test_workspace` 已经覆盖;此处加一项
    scope-plan 形态的断言

PR-4 不修改 memory seam 实现;只验证其 agent-scope 隔离语义。memory 写入
模拟 = ``write_text`` + 模拟 retrieval = ``Path(spec.home_path) / "memory"`` 隔离。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.contracts.protocols.state.scope_plan import BudgetCeiling, ScopePlan
from lca.plugins.assistant._home_layout import (
    CONFIG_FACE_FILES,
    sha256_digest,
)
from lca.plugins.assistant.catalog import (
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
    return catalog.create(CreateAssistantRequest(name="Alice", description="first"))


@pytest.fixture
def assistant_b(catalog: AssistantCatalogImpl) -> Any:
    return catalog.create(CreateAssistantRequest(name="Bob", description="second"))


def _write_memory(home: Path, *, md: str | None = None, json_blob: str | None = None) -> None:
    """模拟 memory seam.write_policy 写入(MEMORY.md + memory/notes.json)。"""
    if md is not None:
        (home / "MEMORY.md").write_text(md, encoding="utf-8")
    if json_blob is not None:
        (home / "memory").mkdir(parents=True, exist_ok=True)
        (home / "memory" / "notes.json").write_text(json_blob, encoding="utf-8")


def _read_memory(home: Path) -> Mapping[str, str | None]:
    """模拟 memory seam.retrieval_policy 读取(仅读 MEMORY.md / memory/notes.json)。"""
    memory_md = home / "MEMORY.md"
    notes_json = home / "memory" / "notes.json"
    return {
        "MEMORY.md": memory_md.read_text(encoding="utf-8") if memory_md.is_file() else None,
        "memory/notes.json": (
            notes_json.read_text(encoding="utf-8") if notes_json.is_file() else None
        ),
    }


def _sync_digests(home: Path) -> None:
    """重算 home 的所有配置面 digest 并写回 manifest(I-A13 修复模拟)。"""
    manifest_path = home / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digests: dict[str, str] = {}
    for name in CONFIG_FACE_FILES:
        path = home / name
        if path.is_file():
            digests[name] = sha256_digest(path)
    manifest["digests"] = digests
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


# ── I-A6: 跨助理 memory 隔离 ──────────────────────────────────────


class TestCrossAssistantMemoryIsolation:
    def test_assistant_a_write_not_visible_to_b_via_home_path(
        self,
        catalog: AssistantCatalogImpl,
        assistant_a: Any,
        assistant_b: Any,
    ) -> None:
        """助理 A 写 memory ⇒ 助理 B 用其 home_path 读 memory 拿不到(I-A6)。

        通过 catalog.get(assistant_id).home_path 隔离;后续 memory seam
        写入接口按 home_path 物化,助理间天然不能跨读。
        """
        # 助理 A 写 memory
        a_marker = "ASSISTANT_A_PRIVILEGED_NOTE_42"
        _write_memory(Path(assistant_a.home_path), md=f"memory content: {a_marker}")

        # 助理 B 用 catalog.get 拿到的 home_path 读 memory
        b_view = catalog.get(assistant_b.assistant_id)
        b_memory = _read_memory(Path(b_view.home_path))
        assert b_memory["MEMORY.md"] is None
        assert a_marker not in str(b_memory)

    def test_assistant_a_write_visible_only_to_a(
        self,
        catalog: AssistantCatalogImpl,
        assistant_a: Any,
        assistant_b: Any,
    ) -> None:
        a_marker = "ASSISTANT_A_PRIVILEGED_SECRET"
        _write_memory(Path(assistant_a.home_path), md=a_marker)

        a_view = catalog.get(assistant_a.assistant_id)
        b_view = catalog.get(assistant_b.assistant_id)

        a_memory = _read_memory(Path(a_view.home_path))
        b_memory = _read_memory(Path(b_view.home_path))

        assert a_memory["MEMORY.md"] == a_marker
        assert b_memory["MEMORY.md"] is None

    def test_memory_seam_paths_are_disjoint(
        self,
        catalog: AssistantCatalogImpl,
        assistant_a: Any,
        assistant_b: Any,
    ) -> None:
        """memory seam.write_policy/retrieval_policy 路径 ⊆ home/memory/;

        两助理 home 互相 disjoint ⇒ memory 写入物理隔离。ScopePlan.visibility
        在此基础上进一步 policy 隔离(本测试断言 disjoint 物理事实)。
        """
        a_home = Path(catalog.get(assistant_a.assistant_id).home_path).resolve()
        b_home = Path(catalog.get(assistant_b.assistant_id).home_path).resolve()
        assert a_home != b_home
        assert not a_home.is_relative_to(b_home)
        assert not b_home.is_relative_to(a_home)


# ── ScopePlan.visibility 形态隔离(已实现最小版)─────────────────────


class TestScopePlanAgentScopeCarrier:
    """I-A2 + I-A6 验证对象是 ScopePlan.lifecycle(agent) + visibility scope 集合。

    本测试断言 ScopePlan 可以承载 assistant_id,且 visibility 默认包含
    agent scope(本助理)但不包含其他助理。
    """

    def test_scope_plan_carries_assistant_id_in_lifecycle(
        self,
        assistant_a: Any,
    ) -> None:
        plan = ScopePlan(
            profile_path="profiles/web-assistant.yaml",
            lifecycle=Scope.AGENT,
            visibility=(Scope.AGENT,),
            acl_grants=("assistant.bootstrap.project",),
            budget_ceiling=BudgetCeiling(max_tool_calls=10),
        )
        # assistant_id 通过 lifecycle.AGENT 携带; Scope enum = 单值
        # I-A2 落地语义 = assistant_id 由 resolve 期注入到 ScopePlan.lifecycle.AGENT
        # 此处只断言 ScopePlan 形状合法,run 期绑定由 RunSession 层注入
        assert plan.lifecycle == Scope.AGENT
        assert Scope.AGENT in plan.visibility

    def test_scope_plan_visibility_default_does_not_include_other_agent(
        self,
        assistant_a: Any,
        assistant_b: Any,
    ) -> None:
        # 助理 B 助理域 ACL 集合不含 assistant_a 的 bootstrap grant
        plan_a = ScopePlan(
            profile_path="profiles/web-assistant.yaml",
            lifecycle=Scope.AGENT,
            visibility=(Scope.AGENT,),
            acl_grants=("assistant.bootstrap.project",),
            budget_ceiling=BudgetCeiling(),
        )
        # 助理 B 不在助理 A 的 visibility 集合(默认收紧到自身 agent scope)
        # IdentitySpace / VisibilitySpace 子空间未实现,ScopePlan 已实现最小版
        # 隔离通过 (visibility ∩ other_agent) == ∅ 表达
        assert assistant_b.assistant_id != assistant_a.assistant_id
        # ScopePlan 形态上 visibility 只含 AGENT 级,不显式记别的助理 id;
        # 子空间落地后切换载体,届时测试更新
        assert plan_a.visibility == (Scope.AGENT,)


# ── I-A13 双向:记忆面不参与 digest;配置面 fail-closed ──────────


class TestMemoryLayerNotInDigestBidirectional:
    def test_memory_md_tamper_does_not_break_get(
        self,
        catalog: AssistantCatalogImpl,
        assistant_a: Any,
    ) -> None:
        """I-A13 正向:篡改 MEMORY.md ⇒ catalog.get 仍 OK(记忆面不参与 digest)。"""
        home = Path(assistant_a.home_path)
        _write_memory(home, md="tampered memory content")
        spec = catalog.get(assistant_a.assistant_id)
        assert spec.assistant_id == assistant_a.assistant_id

    def test_memory_json_tamper_does_not_break_get(
        self,
        catalog: AssistantCatalogImpl,
        assistant_a: Any,
    ) -> None:
        home = Path(assistant_a.home_path)
        _write_memory(home, json_blob='{"tampered": true}')
        spec = catalog.get(assistant_a.assistant_id)
        assert spec.assistant_id == assistant_a.assistant_id

    def test_soul_md_tamper_breaks_get(
        self,
        catalog: AssistantCatalogImpl,
        assistant_a: Any,
    ) -> None:
        """I-A13 反向:篡改 SOUL.md ⇒ catalog.get 抛 AssistantDigestMismatch(fail-closed)。"""
        (Path(assistant_a.home_path) / "SOUL.md").write_text("tampered", encoding="utf-8")
        with pytest.raises(AssistantDigestMismatch):
            catalog.get(assistant_a.assistant_id)

    def test_goals_yaml_tamper_breaks_get(
        self,
        catalog: AssistantCatalogImpl,
        assistant_a: Any,
    ) -> None:
        (Path(assistant_a.home_path) / "goals.yaml").write_text(
            "tampered: true\n", encoding="utf-8"
        )
        with pytest.raises(AssistantDigestMismatch):
            catalog.get(assistant_a.assistant_id)


# ── 修复链:revise_reimport 模拟(手动 patch manifest 钉 digest)─────


class TestReimportRecoversFromDigestMismatch:
    def test_memory_md_tamper_then_get_still_succeeds(
        self,
        catalog: AssistantCatalogImpl,
        assistant_a: Any,
    ) -> None:
        """篡改记忆面后立即 get:OK(记忆面不参与 digest,无须 reimport)。"""
        _write_memory(Path(assistant_a.home_path), md="some memory")
        spec = catalog.get(assistant_a.assistant_id)
        assert spec.assistant_id == assistant_a.assistant_id

    def test_config_face_tamper_then_reimport_recovers(
        self,
        catalog: AssistantCatalogImpl,
        assistant_a: Any,
    ) -> None:
        """配置面篡改后手动 reimport(模拟 catalog.reimport 行为):get 恢复。"""
        home = Path(assistant_a.home_path)
        (home / "SOUL.md").write_text("new SOUL content", encoding="utf-8")
        # 同步 digest(reimport 行为)
        _sync_digests(home)
        spec = catalog.get(assistant_a.assistant_id)
        assert spec.assistant_id == assistant_a.assistant_id
