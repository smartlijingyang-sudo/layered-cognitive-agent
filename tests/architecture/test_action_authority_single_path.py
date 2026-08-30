"""Architecture guards for the plan-owned action-authority path."""

from __future__ import annotations

import pytest

from lca.contracts.models.team.role_team import ToolPermissionManifest
from lca.infrastructure.transport.transport_registry import TransportRegistry
from lca.cognition.body import action_catalog
from lca.cognition.body.action_registry import ActionRegistry
from lca.cognition.body.safe_executor import SimpleSafeExecutor
from lca.cognition.body.simple_body import SimpleBody
from lca.cognition.body.tool_registry import SimpleToolRegistry


def test_action_catalog_does_not_reintroduce_assembly_paths() -> None:
    """The catalog declares vocabulary; authority and handlers assemble actions."""
    assert not hasattr(action_catalog, "_SCOPE_ACTIONS")
    assert not hasattr(action_catalog, "_operation_for")
    assert not hasattr(action_catalog, "build_default_action_registry")


def test_simple_body_requires_a_plan_owned_action_registry() -> None:
    """Execution dependencies alone cannot mint action authority inside Body."""
    tools = SimpleToolRegistry()
    executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[]))
    transport = TransportRegistry()

    with pytest.raises(TypeError, match="action_registry"):
        SimpleBody(tools, executor, transport)  # type: ignore[call-arg]

    body = SimpleBody(
        tool_registry=tools,
        safe_executor=executor,
        transport_registry=transport,
        action_registry=ActionRegistry(),
    )

    assert body.action_registry.allowed_action_types() == []
