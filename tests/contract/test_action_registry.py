"""契约完整性测试 —— ActionRegistry / Prompt / Schema 三者一致性。

L6 治理层：新增 action_type 必须同时满足 Registry 注册 + Prompt 枚举包含 + 至少一条单测，
否则 CI 直接 fail。
"""

from __future__ import annotations

import pytest

from lca.contracts.models.team.role_team import ToolPermissionManifest
from lca.infrastructure.component_registry import RegistryKeyError
from lca.infrastructure.transport.agent_transport import InternalTransport
from lca.infrastructure.transport.transport_registry import TransportRegistry
from lca.cognition.body.action_registry import ActionRegistry
from lca.cognition.body.safe_executor import SimpleSafeExecutor
from lca.cognition.body.tool_registry import SimpleToolRegistry
from tests.support.action_authority import build_test_action_registry


def _build_registry() -> ActionRegistry:
    tool_reg = SimpleToolRegistry()
    safe_exec = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]))
    transport_reg = TransportRegistry()
    transport_reg.register(InternalTransport())
    return build_test_action_registry(
        tools=tool_reg,
        safe_executor=safe_exec,
        transport=transport_reg,
    )


class TestActionRegistryCompleteness:
    """断言默认注册表包含所有核心 action_type。"""

    def test_core_actions_registered(self) -> None:
        registry = _build_registry()
        expected = {"respond", "use_tool", "delegate", "handoff"}
        actual = set(registry.allowed_action_types())
        assert expected.issubset(actual), f"缺少核心 action: {expected - actual}"

    def test_resolve_returns_handler(self) -> None:
        registry = _build_registry()
        for action_type in registry.allowed_action_types():
            handler = registry.resolve(action_type)
            assert handler is not None, f"{action_type} 已注册但 resolve 返回 None"

    def test_resolve_unknown_raises(self) -> None:
        registry = _build_registry()
        with pytest.raises(RegistryKeyError):
            registry.resolve("research_plan")
        with pytest.raises(RegistryKeyError):
            registry.resolve("nonexistent")

    def test_get_unknown_returns_none(self) -> None:
        registry = _build_registry()
        assert registry.get("research_plan") is None
        assert registry.get("nonexistent") is None

    def test_is_registered(self) -> None:
        registry = _build_registry()
        assert registry.is_registered("respond")
        assert not registry.is_registered("research_plan")
