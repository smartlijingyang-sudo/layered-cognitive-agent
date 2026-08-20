"""Team channel wiring — transport registry and in-process member handlers.

Separated from ``spawn.py`` so agent-graph decisions and team transport
wiring can be read independently. Public re-exports stay on ``spawn`` for
call sites that import the composition-root builders.
"""

from __future__ import annotations

from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import AgentTransport
from lca.layer0_infra.transport.a2a_transport import A2ATransport
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.mcp_transport import MCPTransport
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer3_agent.cognitive_agent import CognitiveAgent


def build_default_transport_registry() -> TransportRegistry:
    """Register built-in Internal / A2A / MCP transports for one agent pipeline."""
    registry = TransportRegistry()
    for t in (InternalTransport(), A2ATransport(), MCPTransport()):
        registry.register(t)
    return registry


async def call_member_for_channel(member: CognitiveAgent, subtask: str) -> Observation:
    """Invoke a team member for InternalTransport (preserves delegator role)."""
    from lca.contracts.models.team.delegation_context import get_current_delegator
    from lca.contracts.models.team.run_context import RunContext

    from_role = get_current_delegator()
    result = await member.run(subtask, RunContext(from_role=from_role))
    return Observation.from_result(result)


def build_team_transport(members: list[CognitiveAgent]) -> AgentTransport:
    """Build in-process channel: each member role maps to send_and_wait handler."""
    transport = InternalTransport()
    for member in members:

        async def _handler(subtask: str, _m: CognitiveAgent = member) -> Observation:
            return await call_member_for_channel(_m, subtask)

        transport.register_agent(member.role_profile.role, _handler)
    return transport
