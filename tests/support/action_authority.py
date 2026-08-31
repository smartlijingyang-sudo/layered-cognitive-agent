"""Explicit action-authority fixtures for tests.

Production composition receives action authority from a compiled run plan. These
helpers make tests state the same dependency explicitly instead of relying on
``SimpleBody`` to choose a scope or construct default handlers.
"""

from __future__ import annotations

from lca.cognition.body.action_registry import ActionRegistry
from lca.cognition.body.simple_body import SimpleBody
from lca.cognition.transport_registry_factory import build_transport_registry
from lca.contracts.atoms.enums import ActionType
from lca.contracts.protocols import SafeExecutor, ToolRegistry, TransportRegistryProtocol
from lca.plugins.composer.act.action_authority import build_action_registry_from_authority
from lca.plugins.providers.act.action_handlers import DefaultActionHandlerRegistry

DEFAULT_EXECUTABLE_ACTIONS = frozenset(
    {
        ActionType.RESPOND.value,
        ActionType.USE_TOOL.value,
        ActionType.DELEGATE.value,
        ActionType.HANDOFF.value,
    }
)


def build_test_action_registry(
    *,
    tools: ToolRegistry,
    safe_executor: SafeExecutor,
    transport: TransportRegistryProtocol,
    allowed_actions: frozenset[str] = DEFAULT_EXECUTABLE_ACTIONS,
    forbidden_actions: frozenset[str] = frozenset(),
) -> ActionRegistry:
    """Build test actions through the production authority seam.

    Tests may override the explicit ``allowed_actions`` or ``forbidden_actions``
    inputs when a scenario needs a narrower authority set.
    """
    return build_action_registry_from_authority(
        tools=tools,
        safe_executor=safe_executor,
        transport=transport,
        handler_registry=DefaultActionHandlerRegistry(),
        allowed_actions=allowed_actions,
        forbidden_actions=forbidden_actions,
    )


def build_test_body(
    tools: ToolRegistry,
    safe_executor: SafeExecutor,
    *,
    transport: TransportRegistryProtocol | None = None,
    allowed_actions: frozenset[str] = DEFAULT_EXECUTABLE_ACTIONS,
    forbidden_actions: frozenset[str] = frozenset(),
) -> SimpleBody:
    """Create a Body whose registry is explicitly derived from test authority."""
    resolved_transport = transport or build_transport_registry()
    return SimpleBody(
        tool_registry=tools,
        safe_executor=safe_executor,
        transport_registry=resolved_transport,
        action_registry=build_test_action_registry(
            tools=tools,
            safe_executor=safe_executor,
            transport=resolved_transport,
            allowed_actions=allowed_actions,
            forbidden_actions=forbidden_actions,
        ),
    )


__all__ = [
    "DEFAULT_EXECUTABLE_ACTIONS",
    "build_test_action_registry",
    "build_test_body",
]
