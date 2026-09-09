# PR-D final cleanup — self-contained body provider (no agent_lab dependency)
"""lab.body provider — composes SimpleBody + PipelineSafeExecutor + Transport
for the act phase.

Replaces the deleted agent_lab.nodes.act.execute.body helper. Uses
the LCA SimpleBody / PipelineSafeExecutor / LabToolRegistry / action
authority plugins directly.

delete-when (PR-D final acceptance):
- This provider is the unique composition entry for the act phase.
  When the LCA production path (lca.plugins.composer.act.body_provider)
  absorbs the lab-specific tool registry / transport wiring, this
  module is the merge target.
"""

from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS
from lca.plugins.lab.session.provider.plugin import PLAN_REF


def get_body(allowed_tools=None):
    """Build a SimpleBody instance with the lab tool registry.

    Args:
        allowed_tools: optional whitelist; defaults to all tools in the
            LabToolRegistry. The SimpleToolRegistry is built once per call.

    Composition:
        - PipelineSafeExecutor(ToolPermissionManifest(allowed))
        - SimpleToolRegistry (built from lab.tools.provider.configure())
        - InternalTransport (built from lab.transport.provider.get_transport())
        - SimpleBody(tool_registry, safe_executor, transport, action_registry)
    """
    from lca.cognition.body.executor.pipeline_safe_executor import PipelineSafeExecutor
    from lca.cognition.body.executor.simple_body import SimpleBody
    from lca.cognition.body.tools.tool_registry import SimpleToolRegistry
    from lca.contracts.models.core.policy.budget import Budget
    from lca.contracts.models.core.state.state import AgentState
    from lca.contracts.models.team.role.team import ToolPermissionManifest
    from lca.infrastructure.transport.agent_transport import InternalTransport
    from lca.plugins.composer.act.action_authority import build_action_registry_from_authority
    from lca.plugins.composer.act.body_provider import DefaultActionHandlerRegistry

    from lca.plugins.lab.tools.provider.plugin import get_registry as get_lab_registry
    from lca.plugins.lab.transport.provider.plugin import get_transport

    # 1. Build the lab tool registry -> SimpleToolRegistry copy
    lab_tools = get_lab_registry()
    tools = SimpleToolRegistry()
    for name in lab_tools.names():
        tool = lab_tools.get(name)
        if tool is not None:
            tools.register(tool)

    # 2. Build the safe executor with the allowed tools
    allowed = sorted(allowed_tools) if allowed_tools else sorted(lab_tools.names())
    safe_executor = PipelineSafeExecutor(ToolPermissionManifest(allowed_tools=allowed))

    # 3. Build the transport (lab_echo agent already registered)
    transport = get_transport()

    # 4. Build the action registry (default handlers + call_tool alias)
    action_registry = build_action_registry_from_authority(
        tools=tools,
        safe_executor=safe_executor,
        transport=transport,
        handler_registry=DefaultActionHandlerRegistry(),
        allowed_actions=None,
        forbidden_actions=None,
    )

    # 5. Compose the body
    body = SimpleBody(
        tool_registry=tools,
        safe_executor=safe_executor,
        transport_registry=transport,
        action_registry=action_registry,
    )
    # Expose helpers the caller expects
    body.lab_tools = lambda: lab_tools
    body.plan_ref = lambda: PLAN_REF
    return body


def plan_ref_default() -> str:
    """Default plan_ref for the lab act phase."""
    return PLAN_REF


__all__ = ["get_body", "plan_ref_default"]

# Register loader marker for the capability closure.
_LAB_HOOKS["lab.act.body_provider"] = {"id": "body_provider", "stage": "composition"}