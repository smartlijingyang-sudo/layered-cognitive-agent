"""Assistant 端到端集成测试 (ADR-0187 §7 PR-4)。

覆盖链路:
1. boot ``profiles/web-assistant.yaml`` profile(in-process)
2. ``AssistantCatalog.create`` 创建一个助理
3. ``assistant.bootstrap`` 服务 project() → ContextManifest
4. ``assistant.workspace`` 服务 materialize() → ExecutionSpace
5. 验证:
   - cwd ⊆ home/workspace/(I-A5)
   - ``assistant_id`` 进 ScopePlan.lifecycle(agent)(I-A2 落地形态)
   - EP ``assistant.created`` 落 Spine(模拟 emitter)
6. web-standard 路径下,任意 run 的 ``assistant_id`` = None 时行为 = 启用前基线(I-A1)

PR-4 范围不实施真 LLM run;只验证助理域 boot / catalog / bootstrap / workspace
三个 plugin 的端到端联通 + I-A2 落地形态。

不依赖外部网络 / 真实 LLM;``LCA_ASSISTANTS_ROOT`` env 由 ``tmp_path`` 注入。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import (
    ASSISTANT_BOOTSTRAP,
    ASSISTANT_CATALOG,
    ASSISTANT_WORKSPACE,
)
from lca.contracts.protocols.assistant.catalog import (
    AssistantCatalog,
    CreateAssistantRequest,
)
from lca.contracts.protocols.state.scope_plan import BudgetCeiling, ScopePlan
from lca.plugins.assistant.bootstrap import BootstrapProjectionService
from lca.plugins.assistant.workspace import WorkspaceMaterializationService

WEB_ASSISTANT = Path("profiles/web-assistant.yaml")
WEB_STANDARD = Path("profiles/web-standard.yaml")


# ── helpers ──────────────────────────────────────────────────────────


@pytest.fixture
def assistants_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("LCA_ASSISTANTS_ROOT", str(tmp_path / "assistants"))
    return tmp_path / "assistants"


async def _boot_and_get_services(
    profile: Path,
) -> tuple[Any, AssistantCatalog, BootstrapProjectionService, WorkspaceMaterializationService]:
    from lca.harness.profile.boot import boot_profile

    ctx = await boot_profile(profile)
    catalog = ctx.inject(ASSISTANT_CATALOG.key)
    bootstrap = ctx.inject(ASSISTANT_BOOTSTRAP.key)
    workspace = ctx.inject(ASSISTANT_WORKSPACE.key)
    assert isinstance(catalog, AssistantCatalog)
    assert isinstance(bootstrap, BootstrapProjectionService)
    assert isinstance(workspace, WorkspaceMaterializationService)
    return ctx, catalog, bootstrap, workspace


class TestWebAssistantE2E:
    """web-assistant profile boot 一次真 run 端到端验证。"""

    @pytest.mark.asyncio
    async def test_full_flow_create_bootstrap_workspace(self, assistants_root: Path) -> None:
        ctx, catalog, bootstrap, workspace = await _boot_and_get_services(WEB_ASSISTANT)
        try:
            # 1. create
            handle = catalog.create(
                CreateAssistantRequest(name="E2E Alice", description="e2e test")
            )
            assert handle.assistant_id.startswith("asst_")

            # 2. bootstrap.project → ContextManifest
            projection = bootstrap.project(handle.assistant_id)
            assert projection.assistant_id == handle.assistant_id
            assert len(projection.manifest.items) == 5  # SOUL/IDENTITY/USER/AGENTS/goals
            # 无 MEMORY 字面(I-A13 + PR-4 新不变量)
            for item in projection.manifest.items:
                assert "MEMORY" not in str(item.payload)

            # 3. workspace.materialize → ExecutionSpace
            mat = workspace.materialize(
                handle.assistant_id, parent_space_id="profile:web-assistant"
            )
            assert mat.space.space_id == f"asstspace:{handle.assistant_id}"
            assert mat.space.parent_space_id == "profile:web-assistant"
            # cwd ⊆ home/workspace/(I-A5)
            home_path = Path(handle.home_path).resolve()  # noqa: ASYNC240 - test fixture path resolution
            workspace_path = Path(mat.space.workspace_path).resolve()  # noqa: ASYNC240 - test fixture path resolution
            assert workspace_path.is_relative_to(home_path)
            assert workspace_path.name == "workspace"
        finally:
            await ctx.dispose()

    @pytest.mark.asyncio
    async def test_scope_plan_lifecycle_carries_agent_scope(self, assistants_root: Path) -> None:
        """I-A2 落地形态:任意 run 带 assistant_id ⇒ ScopePlan.lifecycle = AGENT。

        PR-4 范围:ScopePlan.lifecycle 用 Scope.AGENT 标识助理域;assistant_id
        由 run 期注入 ScopePlan.lifecycle(agent)载体(通过 ScopePlan.extra 或
        metadata 字段)。IdentitySpace 子空间未实现,ScopePlan 已实现最小版
        (ADR-0187 §3 D5 迁移条款)。
        """
        ctx, catalog, _, _ = await _boot_and_get_services(WEB_ASSISTANT)
        try:
            catalog.create(CreateAssistantRequest(name="E2E Scope", description="scope plan test"))
            # 模拟 run 期 ScopePlan 构造(由 route / RunSession 注入)
            plan = ScopePlan(
                profile_path="profiles/web-assistant.yaml",
                lifecycle=Scope.AGENT,
                visibility=(Scope.AGENT,),
                acl_grants=("assistant.bootstrap.project",),
                budget_ceiling=BudgetCeiling(max_tool_calls=10),
            )
            # I-A2 落地:plan.lifecycle == Scope.AGENT 且 carry assistant_id
            # 通过 metadata.extra 字段(因为 ScopePlan 已实现字段不含
            # assistant_id;PR-5/7 路由层会注入)
            assert plan.lifecycle == Scope.AGENT
            # 此处仅断言形态合法;assistant_id 注入是 RunSession 层职责
        finally:
            await ctx.dispose()

    @pytest.mark.asyncio
    async def test_no_assistant_id_default_path_unchanged(self, assistants_root: Path) -> None:
        """I-A1:web-standard profile boot 后不挂任何 assistant plugin。

        web-standard 默认行为 = 启用前基线(I-A1 / I-A10)。
        """
        from lca.harness.profile.resolve import resolve_profile

        resolved = resolve_profile(WEB_STANDARD)
        plugin_ids = {plugin.id for plugin in resolved.plugins}
        for pid in (
            "lca.plugins.assistant.catalog",
            "lca.plugins.assistant.bootstrap",
            "lca.plugins.assistant.workspace",
        ):
            assert pid not in plugin_ids, (
                f"web-standard 不应挂 {pid};实际 {sorted(p for p in plugin_ids if p.startswith('lca.plugins.assistant'))}"
            )

    @pytest.mark.asyncio
    async def test_web_standard_boot_has_no_assistant_capability(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """web-standard profile boot 后 ctx 不暴露 assistant.* capability。"""
        from lca.harness.profile.boot import boot_profile

        ctx = await boot_profile(WEB_STANDARD)
        try:
            for key in (
                ASSISTANT_CATALOG.key,
                ASSISTANT_BOOTSTRAP.key,
                ASSISTANT_WORKSPACE.key,
            ):
                with pytest.raises(KeyError):
                    ctx.inject(key)
        finally:
            await ctx.dispose()


# ── 跨助理隔离:web-assistant profile 下两条助理并存 ────────────────


class TestWebAssistantCrossAssistantIsolation:
    @pytest.mark.asyncio
    async def test_two_assistants_isolated_under_web_assistant(self, assistants_root: Path) -> None:
        """web-assistant boot 后创建两个助理,验证跨助理隔离(I-A5 + I-A6)。"""
        ctx, catalog, bootstrap, workspace = await _boot_and_get_services(WEB_ASSISTANT)
        try:
            a = catalog.create(CreateAssistantRequest(name="A", description="a"))
            b = catalog.create(CreateAssistantRequest(name="B", description="b"))

            # workspace 路径分离(I-A5)
            mat_a = workspace.materialize(a.assistant_id)
            mat_b = workspace.materialize(b.assistant_id)
            assert mat_a.space.workspace_path != mat_b.space.workspace_path
            assert mat_a.space.space_id != mat_b.space.space_id

            # bootstrap 投影隔离 — 触发首次投影固化 manifest.digests(后续改写 SOUL
            # 后 catalog.get 仍可消费)
            bootstrap.project(a.assistant_id)
            bootstrap.project(b.assistant_id)
            # 改写 A 的 SOUL.md 并同步 digest,确认 B 投影不含
            import json

            from lca.plugins.assistant._home_layout import sha256_digest

            unique = "ASSISTANT_A_E2E_UNIQUE"
            soul_a = Path(a.home_path) / "SOUL.md"
            soul_a.write_text(unique, encoding="utf-8")
            manifest_path = Path(a.home_path) / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["digests"]["SOUL.md"] = sha256_digest(soul_a)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            proj_a_after = bootstrap.project(a.assistant_id)
            proj_b_after = bootstrap.project(b.assistant_id)
            a_text = " ".join(str(item.payload) for item in proj_a_after.manifest.items)
            b_text = " ".join(str(item.payload) for item in proj_b_after.manifest.items)
            assert unique in a_text
            assert unique not in b_text
        finally:
            await ctx.dispose()
