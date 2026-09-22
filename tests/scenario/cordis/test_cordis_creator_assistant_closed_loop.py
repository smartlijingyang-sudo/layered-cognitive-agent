"""Comprehensive E2E Closed-Loop Suite: 5 Rich Scenarios for Creator Mode & Assistant Home.

Scenarios:
1. Data engineering preset creation and private home persistence.
2. Same-session zero-restart trigger through ToolsService & SafeExecutor.
3. Cross-session perception and replay without cordis_control invocation.
4. Cross-agent sharing and inheritance via PresetPromotionService.
5. Hot upgrade and safe rollback self-healing lifecycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cordis import Context

from lca.application.preset.promotion import PresetPromotionService
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.result import ToolExecutionError
from lca.contracts.models.observability.journal.journal import (
    PluginAuthored,
    PluginMounted,
    PluginUnmounted,
)
from lca.contracts.models.preset.package import AuthoredPlugin, PresetPackage, PresetScope
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols import Tool
from lca.infrastructure.capability.tools.tools import ToolsService
from lca.infrastructure.observability.backends.journal_backend import MemoryJournal
from lca.infrastructure.observability.facade import BoundObservability, bind_backends
from lca.infrastructure.preset.discovery import AssistantPresetDiscovery, PresetStatus
from lca.infrastructure.preset.fs_repository import FileSystemPresetRepository
from lca.infrastructure.tools.dynamic.bridge import DynamicToolBridge
from lca.plugins.composer.composition.cordis_composer import (
    CordisComposer,
    build_default_invariant_checker,
)
from lca.plugins.prompts.sections import AutonomousPresetsSection
from lca.plugins.tools.cordis_control import build_cordis_control_tool


class DummySafeExecutor:
    """Simulates SafeExecutor with ToolPermissionManifest governance (C5 & C10)."""

    def __init__(self, allowed_tools: list[str]) -> None:
        self.permission_manifest = ToolPermissionManifest(allowed_tools=list(allowed_tools))

    async def execute(self, tool: Tool, args: dict[str, Any]) -> Observation:
        if tool.name not in self.permission_manifest.allowed_tools:
            raise ToolExecutionError(
                f"工具 {tool.name!r} 未在 ToolPermissionManifest.allowed_tools 中授权"
            )
        return await tool.execute(args)


def _write_funnel_source(path: Path, *, v2: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not v2:
        code = '''
plugin_meta = {
    "name": "funnel_analytics",
    "layer": "behavior",
    "implements": ["Plugin", "Tool"],
    "capabilities": ["analytics.funnel"],
    "side_effects": "none",
    "policy_class": "execute",
    "description": "Calculate conversion rates across sequential funnel steps",
}

def factory():
    def funnel_analytics(counts: list[int]) -> dict:
        """Calculate conversion rates across sequential funnel steps."""
        if not counts or len(counts) < 2:
            return {"conversion_rates": []}
        rates = []
        for i in range(len(counts) - 1):
            prev = counts[i]
            nxt = counts[i + 1]
            rate = round(nxt / prev, 4) if prev > 0 else 0.0
            rates.append(rate)
        return {"conversion_rates": rates}
    return funnel_analytics
'''
    else:
        code = '''
plugin_meta = {
    "name": "funnel_analytics",
    "layer": "behavior",
    "implements": ["Plugin", "Tool"],
    "capabilities": ["analytics.funnel"],
    "side_effects": "none",
    "policy_class": "execute",
    "description": "Calculate conversion rates and total dropoff across funnel steps (v2)",
}

def factory():
    def funnel_analytics(counts: list[int]) -> dict:
        """Calculate conversion rates and total dropoff across funnel steps (v2)."""
        if not counts or len(counts) < 2:
            return {"conversion_rates": [], "total_dropoff": 0}
        rates = []
        for i in range(len(counts) - 1):
            prev = counts[i]
            nxt = counts[i + 1]
            rate = round(nxt / prev, 4) if prev > 0 else 0.0
            rates.append(rate)
        dropoff = counts[0] - counts[-1]
        return {"conversion_rates": rates, "total_dropoff": dropoff}
    return funnel_analytics
'''
    path.write_text(code.strip(), encoding="utf-8")


# ── Scenario 1: Data engineering preset creation & private home persistence ───────


@pytest.mark.asyncio
async def test_scenario_1_data_engineering_preset_creation(tmp_path: Path) -> None:
    """Scenario 1: Agent creates complex funnel analytics preset in assistant_home."""
    assistant_home = tmp_path / "assistants" / "asst_analytics_01"
    assistant_home.mkdir(parents=True)
    scratch_file = tmp_path / "scratch" / "funnel_analytics.py"
    _write_funnel_source(scratch_file)

    journal = MemoryJournal()
    obs = BoundObservability(journal=journal)

    with bind_backends(obs):
        ctx = Context()
        composer = CordisComposer(ctx, invariant_checker=build_default_invariant_checker())
        control_tool = build_cordis_control_tool(
            composer=composer,
            caller_grant=(
                "cordis_control.author",
                "cordis_control.validate",
                "cordis_control.promote",
                "analytics.funnel",
            ),
            actor_role="arch-creator",
            assistant_home=assistant_home,
        )

        # 1. Author
        res_author = await control_tool.execute({
            "action": "author",
            "name": "funnel_analytics",
            "path": str(scratch_file),
        })
        assert res_author.success is True
        assert res_author.payload["artifact"]["state"] == "draft"

        # 2. Validate
        res_val = await control_tool.execute({
            "action": "validate",
            "name": "funnel_analytics",
        })
        assert res_val.success is True
        assert res_val.payload["artifact"]["state"] == "verified"

        # 3. Promote to agent scope
        res_promote = await control_tool.execute({
            "action": "promote",
            "name": "funnel_analytics",
            "target_scope": "agent",
            "preset_id": "clickstream_kit",
        })
        assert res_promote.success is True
        assert res_promote.payload["face"] == "promote"

        # Verification 1: Filesystem persistence under assistant_home (INV-AP01)
        preset_dir = assistant_home / "presets" / "clickstream_kit"
        assert preset_dir.is_dir()
        assert (preset_dir / "bundle.yaml").is_file()
        assert (preset_dir / "plugins" / "funnel_analytics.py").is_file()
        assert (preset_dir / "preset.json").is_file()

        # Direct autonomous plugin copy
        assert (assistant_home / "plugins" / "funnel_analytics.py").is_file()

        # Verification 2: Typed JournalEvents recorded in sequence (INV-C3)
        events = [s.event for s in journal.store.events]
        event_types = [type(e) for e in events]
        assert PluginAuthored in event_types
        assert PluginMounted in event_types


# ── Scenario 2: Same-session zero-restart trigger ───────────────────────────────


@pytest.mark.asyncio
async def test_scenario_2_same_session_zero_restart_trigger(tmp_path: Path) -> None:
    """Scenario 2: Newly promoted tool is immediately executable in same session."""
    assistant_home = tmp_path / "assistants" / "asst_analytics_01"
    assistant_home.mkdir(parents=True)
    scratch_file = tmp_path / "scratch" / "funnel_analytics.py"
    _write_funnel_source(scratch_file)

    journal = MemoryJournal()
    obs = BoundObservability(journal=journal)

    with bind_backends(obs):
        tools_service = ToolsService()
        safe_executor = DummySafeExecutor(allowed_tools=["builtin_bash"])

        ctx = Context()
        composer = CordisComposer(ctx, invariant_checker=build_default_invariant_checker())
        control_tool = build_cordis_control_tool(
            composer=composer,
            caller_grant=(
                "cordis_control.author",
                "cordis_control.validate",
                "cordis_control.promote",
                "analytics.funnel",
            ),
            actor_role="arch-creator",
            assistant_home=assistant_home,
            tools_service=tools_service,
            safe_executor=safe_executor,
        )

        # Execute promote lifecycle
        r1 = await control_tool.execute({
            "action": "author",
            "name": "funnel_analytics",
            "path": str(scratch_file),
        })
        assert r1.success is True
        r2 = await control_tool.execute({"action": "validate", "name": "funnel_analytics"})
        assert r2.success is True
        r3 = await control_tool.execute({
            "action": "promote",
            "name": "funnel_analytics",
            "target_scope": "agent",
            "preset_id": "clickstream_kit",
        })
        assert r3.success is True

        # Zero-restart verification: tool is in tools_service & safe_executor allowed_tools
        new_tool = tools_service.get("funnel_analytics")
        assert new_tool is not None
        assert new_tool.name == "funnel_analytics"
        assert "funnel_analytics" in safe_executor.permission_manifest.allowed_tools

        # Execute immediately through SafeExecutor
        obs_res = await safe_executor.execute(new_tool, {"counts": [1000, 500, 100]})
        assert obs_res.success is True
        assert obs_res.payload == {"conversion_rates": [0.5, 0.2]}

        # Invariant check: C5 monotone authorization boundary
        unauthorized = DynamicToolBridge.bridge_callable("rogue_tool", lambda: "hack")
        with pytest.raises(ToolExecutionError, match=r"未在 ToolPermissionManifest.allowed_tools 中授权"):
            await safe_executor.execute(unauthorized, {})


# ── Scenario 3: Cross-session perception and replay ─────────────────────────────


@pytest.mark.asyncio
async def test_scenario_3_cross_session_perception_and_replay(tmp_path: Path) -> None:
    """Scenario 3: New session starts; agent perceives preset via prompt & invokes with 0 control calls."""
    assistant_home = tmp_path / "assistants" / "asst_analytics_01"
    assistant_home.mkdir(parents=True)

    # 1. Pre-populate assistant_home with clickstream_kit
    repo = FileSystemPresetRepository()
    plugin_file = tmp_path / "scratch" / "funnel_analytics.py"
    _write_funnel_source(plugin_file)
    plugin = AuthoredPlugin(
        name="funnel_analytics",
        code=plugin_file.read_text(encoding="utf-8"),
        capabilities=("analytics.funnel",),
        side_effects="none",
        policy_class="execute",
    )
    package = PresetPackage(
        preset_id="clickstream_kit",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_analytics_01",
        description="Clickstream conversion toolkit",
        plugins=(plugin,),
    )
    repo.save(package, assistant_home=assistant_home)

    # 2. Simulate fresh session startup (completely empty in-memory state)
    discovery = AssistantPresetDiscovery(assistant_home=assistant_home)
    discovered = discovery.discover_presets()
    assert len(discovered) == 1
    assert discovered[0].preset_id == "clickstream_kit"
    assert discovered[0].status == PresetStatus.ACTIVE

    # 3. Prompt perception check: AutonomousPresetsSection renders description
    role_profile = RoleProfile(
        role="data_analyst",
        goal="funnel analysis",
        backstory="expert analyst",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
        extra={"assistant_home_path": str(assistant_home)},
    )
    section = AutonomousPresetsSection()
    prompt_out = section.render(
        role_profile=role_profile,
        task="analyze clickstream",
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    )
    assert "<autonomous_presets>" in prompt_out.text
    assert "clickstream_kit" in prompt_out.text
    assert "funnel_analytics" in prompt_out.text

    # 4. Zero-control invocation: tools materialized without cordis_control
    tools = discovery.discover_tools()
    assert len(tools) == 1
    funnel_tool = tools[0]
    assert funnel_tool.name == "funnel_analytics"

    obs = await funnel_tool.execute({"counts": [2000, 1000, 200]})
    assert obs.success is True
    assert obs.payload == {"conversion_rates": [0.5, 0.2]}


# ── Scenario 4: Cross-agent sharing and inheritance ─────────────────────────────


@pytest.mark.asyncio
async def test_scenario_4_cross_agent_sharing_and_inheritance(tmp_path: Path) -> None:
    """Scenario 4: Agent A shares preset to shared library; Agent B inherits and executes it."""
    home_a = tmp_path / "assistants" / "asst_analytics_01"
    home_a.mkdir(parents=True)
    home_b = tmp_path / "assistants" / "asst_reviewer_02"
    home_b.mkdir(parents=True)
    shared_root = tmp_path / "shared" / "presets"
    shared_root.mkdir(parents=True)

    # 1. Agent A creates private preset
    repo = FileSystemPresetRepository(shared_root=shared_root)
    plugin_file = tmp_path / "scratch" / "funnel_analytics.py"
    _write_funnel_source(plugin_file)
    package = PresetPackage(
        preset_id="clickstream_kit",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_analytics_01",
        description="Shared clickstream analysis toolkit",
        plugins=(
            AuthoredPlugin(
                name="funnel_analytics",
                code=plugin_file.read_text(encoding="utf-8"),
                capabilities=("analytics.funnel",),
                side_effects="none",
                policy_class="execute",
            ),
        ),
    )
    repo.save(package, assistant_home=home_a)

    # 2. Agent A promotes preset to shared
    promotion_service = PresetPromotionService(repository=repo, shared_root=shared_root)
    promo_result = promotion_service.promote_to_shared("clickstream_kit", assistant_home=home_a)

    assert promo_result.scope == PresetScope.SHARED
    assert (shared_root / "clickstream_kit" / "bundle.yaml").is_file()

    # 3. Agent B starts with empty private directory, but accesses shared repository
    shared_pkg = repo.find_by_id("clickstream_kit", scope=PresetScope.SHARED)
    assert shared_pkg is not None
    assert shared_pkg.assistant_id == "asst_analytics_01"

    # 4. Agent B loads and materializes the inherited tool
    inherited_discovery = AssistantPresetDiscovery(
        assistant_home=shared_root.parent,
        repository=repo,
    )
    shared_dir = shared_root / "clickstream_kit"
    tool = inherited_discovery._load_plugin_tool(shared_dir, shared_pkg.plugins[0])
    assert tool is not None
    assert tool.name == "funnel_analytics"

    # 5. Agent B executes inherited expert capability
    obs = await tool.execute({"counts": [5000, 2500, 500]})
    assert obs.success is True
    assert obs.payload == {"conversion_rates": [0.5, 0.2]}


# ── Scenario 5: Hot upgrade and safe rollback ───────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_5_hot_upgrade_and_safe_rollback(tmp_path: Path) -> None:
    """Scenario 5: Dynamic hot upgrade to v2 and safe rollback to baseline."""
    assistant_home = tmp_path / "assistants" / "asst_analytics_01"
    assistant_home.mkdir(parents=True)
    v1_file = tmp_path / "scratch" / "v1.py"
    v2_file = tmp_path / "scratch" / "v2.py"
    _write_funnel_source(v1_file, v2=False)
    _write_funnel_source(v2_file, v2=True)

    journal = MemoryJournal()
    obs_b = BoundObservability(journal=journal)

    with bind_backends(obs_b):
        tools_service = ToolsService()
        safe_executor = DummySafeExecutor(allowed_tools=["builtin_bash"])

        ctx = Context()
        composer = CordisComposer(ctx, invariant_checker=build_default_invariant_checker())
        control_tool = build_cordis_control_tool(
            composer=composer,
            caller_grant=(
                "cordis_control.author",
                "cordis_control.validate",
                "cordis_control.promote",
                "analytics.funnel",
            ),
            actor_role="arch-creator",
            assistant_home=assistant_home,
            tools_service=tools_service,
            safe_executor=safe_executor,
        )

        # 1. Mount v1
        r_a1 = await control_tool.execute({
            "action": "author",
            "name": "funnel_analytics",
            "path": str(v1_file),
        })
        assert r_a1.success is True
        r_v1 = await control_tool.execute({"action": "validate", "name": "funnel_analytics"})
        assert r_v1.success is True
        res_v1 = await control_tool.execute({
            "action": "promote",
            "name": "funnel_analytics",
            "target_scope": "agent",
            "preset_id": "clickstream_kit",
        })
        assert res_v1.success is True

        # Test v1 output
        tool_v1 = DynamicToolBridge.bridge_instance(
            "funnel_analytics",
            composer._ctx.own_bindings["plugin:funnel_analytics"],
        )
        obs_v1 = await tool_v1.execute({"counts": [100, 50, 10]})
        assert obs_v1.payload == {"conversion_rates": [0.5, 0.2]}
        assert "total_dropoff" not in obs_v1.payload

        # 2. Hot upgrade to v2: retire v1 and mount enhanced v2
        res_retire = await control_tool.execute({
            "action": "promote",
            "name": "funnel_analytics",
            "rollback": True,
        })
        assert res_retire.success is True

        r_a2 = await control_tool.execute({
            "action": "author",
            "name": "funnel_analytics",
            "path": str(v2_file),
        })
        assert r_a2.success is True
        r_v2 = await control_tool.execute({"action": "validate", "name": "funnel_analytics"})
        assert r_v2.success is True
        res_v2 = await control_tool.execute({
            "action": "promote",
            "name": "funnel_analytics",
            "target_scope": "agent",
            "preset_id": "clickstream_kit",
        })
        assert res_v2.success is True

        # Test v2 hot replaced output
        tool_v2 = DynamicToolBridge.bridge_instance(
            "funnel_analytics",
            composer._ctx.own_bindings["plugin:funnel_analytics"],
        )
        obs_v2 = await tool_v2.execute({"counts": [100, 50, 10]})
        assert obs_v2.payload["total_dropoff"] == 90

        # 3. Safe Rollback
        res_rollback = await control_tool.execute({
            "action": "promote",
            "name": "funnel_analytics",
            "rollback": True,
        })
        assert res_rollback.success is True
        assert res_rollback.payload["artifact"]["state"] == "retired"

        # SafeExecutor & ToolsService synchronization check on retirement (C5 capability revocation)
        assert tools_service.get("funnel_analytics") is None
        assert "funnel_analytics" not in safe_executor.permission_manifest.allowed_tools
        with pytest.raises(ToolExecutionError, match=r"未在 ToolPermissionManifest.allowed_tools 中授权"):
            await safe_executor.execute(tool_v2, {"counts": [100, 50, 10]})

        # Journal contains PluginUnmounted fact
        events = [s.event for s in journal.store.events]
        unmounted_events = [e for e in events if isinstance(e, PluginUnmounted)]
        assert len(unmounted_events) >= 1
        assert unmounted_events[-1].plugin_name == "funnel_analytics"
