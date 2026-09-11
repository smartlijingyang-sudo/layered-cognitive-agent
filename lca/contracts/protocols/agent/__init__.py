"""Agent client protocol — the seam between the graph kernel and agent
collaboration machinery.

The framework talks to :class:`AgentClient`; cognition implements
it via :class:`lca.cognition.wire.agent_client_adapter.AgentClientAdapter`,
which delegates to the existing team / collaboration plugins.

This package contains protocols only. No business DTO knowledge.

What lives here:

- :mod:`client` — :class:`AgentClient` Protocol + :class:`AgentRequest`
  / :class:`AgentResponse` typed envelopes.

What does NOT live here:

- Brain / reasoner / decision-making logic (lives in cognition).
- The graph kernel (lives in framework.graph).
- Plugin implementations (live in plugins/collaboration).
"""
from lca.contracts.protocols.agent.client import (
    AgentClient,
    AgentRequest,
    AgentResponse,
)

__all__ = [
    "AgentClient",
    "AgentRequest",
    "AgentResponse",
]