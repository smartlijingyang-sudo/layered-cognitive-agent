"""Build an executable action registry from plan-derived authority."""

from __future__ import annotations

from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.contracts.protocols.action_handler import ActionHandlerRegistry
from lca.contracts.protocols.infra import (
    SafeExecutor,
    ToolRegistry,
    TransportRegistryProtocol,
)
from lca.layer1_cognitive.body.action_registry import ActionRegistry


def build_action_registry_from_authority(
    *,
    tools: ToolRegistry,
    safe_executor: SafeExecutor,
    transport: TransportRegistryProtocol,
    handler_registry: ActionHandlerRegistry,
    allowed_actions: frozenset[str],
    forbidden_actions: frozenset[str],
) -> ActionRegistry:
    """Build an ActionRegistry from plan authority and provider handlers.

    The plan owns permission while the provider registry owns implementations.
    Any missing or non-creatable implementation fails closed at composition time.
    """
    registry = ActionRegistry()
    required_actions = sorted(allowed_actions - forbidden_actions)
    registered_actions = frozenset(handler_registry.registered())
    missing_actions = [
        action_type for action_type in required_actions if action_type not in registered_actions
    ]
    if missing_actions:
        raise MissingCapabilityError(
            "action authority requires registered handlers: " + ", ".join(missing_actions)
        )

    for action_type in required_actions:
        handler = handler_registry.resolve(action_type)
        if handler is None:
            raise MissingCapabilityError(
                f"action authority handler lookup returned no handler: {action_type}"
            )
        operation = handler.create(tools, safe_executor, transport)
        if operation is None:
            raise MissingCapabilityError(
                f"action authority handler cannot create action: {action_type}"
            )
        registry.register(action_type, operation)
    return registry


__all__ = ["build_action_registry_from_authority"]
