"""Plan-bound composition for the execution act cluster."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.capabilities import (
    ACTION_HANDLERS,
    BODIES,
    HOOKS,
    SAFE_EXECUTOR_SIMPLE,
    TOOLS_COMPOSE_SERVICE,
    TRANSPORT,
)
from lca.contracts.harness.composition.composer import (
    AgentCompositionRequest,
    AgentGraphContribution,
)
from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.plugins.composer.act.action_authority import build_action_registry_from_authority
from lca.plugins.composer.collaboration.team import fork_transport

if TYPE_CHECKING:
    from cordis import Context


class BodyComposer:
    """Compose only the execution cluster of a plan-bound AgentGraph.

    This execution-plane module is the sole local owner of tool registration,
    action-authority filtering, transport forking, Body selection, and Hook
    selection. The immutable request supplies all profile and plan choices;
    this module never chooses a concrete fallback on their behalf.
    """

    key = "body"

    def compose_agent(
        self, request: AgentCompositionRequest, scope: Context
    ) -> AgentGraphContribution:
        """Return the graph contribution selected for this Agent's act cluster."""

        tools = require_capability(scope, TOOLS_COMPOSE_SERVICE.key)()
        for tool in request.spec.tools:
            tools.register(tool)
        safe_executor = require_capability(scope, SAFE_EXECUTOR_SIMPLE.key)(
            request.spec.profile.tool_permission_manifest
        )
        transport = fork_transport(
            require_capability(scope, TRANSPORT.key), request.team_channel, scope
        )
        handler_registry = require_capability(scope, ACTION_HANDLERS.key)
        registry = build_action_registry_from_authority(
            tools=tools,
            safe_executor=safe_executor,
            transport=transport,
            handler_registry=handler_registry,
            allowed_actions=request.allowed_actions,
            forbidden_actions=request.forbidden_actions,
        )
        body_factory = require_capability(scope, BODIES.key)
        body_key = request.spec.body
        try:
            body = body_factory.create(
                body_key,
                tool_registry=tools,
                safe_executor=safe_executor,
                transport_registry=transport,
                action_registry=registry,
            )
        except KeyError as exc:
            raise MissingCapabilityError(
                f"body {body_key!r} not registered in {BODIES.key}"
            ) from exc
        hook_factory = require_capability(scope, HOOKS.key)
        hook_key = request.spec.hooks
        try:
            hooks = hook_factory.create(hook_key)
        except KeyError as exc:
            raise MissingCapabilityError(
                f"hook registry {hook_key!r} not registered in {HOOKS.key}"
            ) from exc
        return AgentGraphContribution(
            brain=None,
            body=body,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=hooks,
            observability=None,
            llm=None,
            phase_capabilities={},
            metadata={"composer": self.key},
        )


__all__ = ["BodyComposer"]
