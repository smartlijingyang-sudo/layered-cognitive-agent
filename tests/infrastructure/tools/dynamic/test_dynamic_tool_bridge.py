"""Tests for DynamicPluginToolAdapter and DynamicToolBridge."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.team.role.team import ToolPermissionManifest
from lca.infrastructure.capability.tools.tools import ToolsService
from lca.infrastructure.tools.dynamic.bridge import (
    DynamicToolBridge,
)


class DummySafeExecutor:
    """Mock safe executor with ToolPermissionManifest for testing dynamic C5 sync."""

    def __init__(self, allowed_tools: list[str]) -> None:
        self.permission_manifest = ToolPermissionManifest(allowed_tools=allowed_tools)

    async def execute(self, tool: Any, args: dict[str, Any]) -> Observation:
        if tool.name not in self.permission_manifest.allowed_tools:
            from lca.contracts.models.core.execution.result import ToolExecutionError

            raise ToolExecutionError(
                f"工具 {tool.name} 未在 ToolPermissionManifest.allowed_tools 中授权",
                Observation(observation_id="denied", success=False, payload=None, error="unauthorized"),
            )
        return await tool.execute(args)


def test_bridge_callable_to_tool() -> None:
    def add_numbers(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    tool = DynamicToolBridge.bridge_callable(
        name="add_numbers",
        func=add_numbers,
        description="Add two numbers",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
    )

    assert tool.name == "add_numbers"
    assert tool.description == "Add two numbers"
    assert "a" in tool.parameters["properties"]

    # Execute sync function wrapped in async execute
    obs = asyncio.run(tool.execute({"a": 10, "b": 25}))
    assert obs.success is True
    assert obs.payload == 35


def test_mount_and_register_active_runtime() -> None:
    tools_service = ToolsService()
    safe_executor = DummySafeExecutor(allowed_tools=["builtin_read"])

    def multiply(x: int, y: int) -> int:
        return x * y

    tool = DynamicToolBridge.bridge_callable("multiply", multiply)

    # Before registration
    assert tools_service.get("multiply") is None
    assert "multiply" not in safe_executor.permission_manifest.allowed_tools

    # Register via DynamicToolBridge
    DynamicToolBridge.register_tool(
        tool,
        tools_service=tools_service,
        safe_executor=safe_executor,
    )

    # After registration: both tools_service and safe_executor updated
    retrieved = tools_service.get("multiply")
    assert retrieved is not None
    assert retrieved.name == "multiply"
    assert "multiply" in safe_executor.permission_manifest.allowed_tools

    # Execution through safe_executor succeeds
    obs = asyncio.run(safe_executor.execute(retrieved, {"x": 6, "y": 7}))
    assert obs.success is True
    assert obs.payload == 42


def test_unauthorized_dynamic_execution_blocked() -> None:
    def secret_tool() -> str:
        return "secret"

    tool = DynamicToolBridge.bridge_callable("secret_tool", secret_tool)
    safe_executor = DummySafeExecutor(allowed_tools=["builtin_read"])

    from lca.contracts.models.core.execution.result import ToolExecutionError

    with pytest.raises(ToolExecutionError, match=r"未在 ToolPermissionManifest.allowed_tools 中授权"):
        asyncio.run(safe_executor.execute(tool, {}))


@pytest.mark.asyncio
async def test_cordis_control_promote_auto_bridges(tmp_path: Path) -> None:
    from cordis import Context

    from lca.plugins.composer.composition.cordis_composer import (
        CordisComposer,
        build_default_invariant_checker,
    )
    from lca.plugins.tools.cordis_control import build_cordis_control_tool
    from tests.scenario.cordis.test_cordis_creator_e2e import bind_journal

    ctx = Context()
    composer = CordisComposer(ctx, invariant_checker=build_default_invariant_checker())
    tools_service = ToolsService()
    safe_executor = DummySafeExecutor(
        allowed_tools=["cordis_control", "tool_fs.read", "tool_fs.write"]
    )

    preset_root = tmp_path / "scratch_preset"
    preset_root.mkdir()
    plugin_path = preset_root / "dynamic_sum.py"
    plugin_path.write_text(
        '''
plugin_meta = {
    "name": "dynamic_sum",
    "layer": "behavior",
    "implements": ["Plugin"],
    "capabilities": ["tool_fs.read"],
    "side_effects": "none",
    "policy_class": "execute",
}

def factory():
    def _sum(items):
        return sum(items)
    return _sum
''',
        encoding="utf-8",
    )

    with bind_journal():
        tool = build_cordis_control_tool(
            composer=composer,
            caller_grant=("cordis_control.author", "cordis_control.validate", "cordis_control.promote", "tool_fs.read"),
            actor_role="cordis-creator",
            preset_root=preset_root,
            tools_service=tools_service,
            safe_executor=safe_executor,
        )

        # 1. Author
        res_author = await tool.execute(
            {"action": "author", "name": "dynamic_sum", "path": str(plugin_path)}
        )
        assert res_author.success

        # 2. Validate
        res_val = await tool.execute({"action": "validate", "name": "dynamic_sum"})
        assert res_val.success

        # 3. Promote
        res_promote = await tool.execute(
            {"action": "promote", "name": "dynamic_sum", "target_scope": "run"}
        )
        assert res_promote.success

        # 4. Verify immediate bridge into tools_service & safe_executor
        bridged_tool = tools_service.get("dynamic_sum")
        assert bridged_tool is not None, "dynamic_sum should be bridged into ToolsService immediately"
        assert "dynamic_sum" in safe_executor.permission_manifest.allowed_tools

        # 5. Execute immediately through safe_executor
        res_exec = await safe_executor.execute(bridged_tool, {"items": [1, 2, 3, 4, 5]})
        assert res_exec.success is True
        assert res_exec.payload == 15
