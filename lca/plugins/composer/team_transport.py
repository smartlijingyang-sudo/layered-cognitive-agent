"""Team transport assembly used by the collaboration composer."""

from __future__ import annotations

from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import AgentTransport
from lca.layer0_infra.transport.a2a_transport import A2ATransport
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.mcp_transport import MCPTransport
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer3_agent.cognitive_agent import CognitiveAgent


def build_default_transport_registry() -> TransportRegistry:
    """Register built-in Internal, A2A, and MCP transports for one Agent pipeline."""

    registry = TransportRegistry()
    for transport in (InternalTransport(), A2ATransport(), MCPTransport()):
        registry.register(transport)
    return registry


async def call_member_for_channel(member: CognitiveAgent, subtask: str) -> Observation:
    """Invoke a team member while preserving the delegator role."""

    from lca.contracts.models.team.delegation_context import get_current_delegator
    from lca.contracts.models.team.run_context import RunContext

    result = await member.run(subtask, RunContext(from_role=get_current_delegator()))
    return Observation.from_result(result)


def build_team_transport(members: list[CognitiveAgent]) -> AgentTransport:
    """Build one in-process transport mapped by member role."""

    transport = InternalTransport()
    for member in members:

        async def handler(subtask: str, agent: CognitiveAgent = member) -> Observation:
            return await call_member_for_channel(agent, subtask)

        transport.register_agent(member.role_profile.role, handler)
    return transport


__all__ = ["build_default_transport_registry", "build_team_transport", "call_member_for_channel"]
