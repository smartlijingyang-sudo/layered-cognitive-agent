"""Subagent registration and lifecycle contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from lca.contracts.harness.collaboration.agent import AgentHandle, AgentIdentity, AgentOptions


@dataclass(frozen=True)
class SubagentCapabilities:
    """Declared capabilities and delegation limits for a subagent kind."""

    capabilities: frozenset[str]
    tools_allow: frozenset[str] = frozenset()
    tools_deny: frozenset[str] = frozenset()
    max_delegation_depth: int = 1


@dataclass(frozen=True)
class SubagentSpec:
    """A named subagent implementation available for activation."""

    name: str
    capabilities: SubagentCapabilities


@dataclass(frozen=True)
class SubagentRequest:
    """A negotiated request to activate a child agent."""

    name: str
    parent: AgentIdentity
    required_capabilities: frozenset[str] = frozenset()
    requested_tools: frozenset[str] = frozenset()
    options: AgentOptions = field(default_factory=AgentOptions)


@dataclass(frozen=True)
class ActivatedSubagent:
    """The child handle and its immutable lineage identity."""

    identity: AgentIdentity
    handle: AgentHandle
    capabilities: SubagentCapabilities


class SubagentActivator(Protocol):
    """Creates one child after registry capability negotiation."""

    async def __call__(
        self,
        spec: SubagentSpec,
        identity: AgentIdentity,
        options: AgentOptions,
    ) -> AgentHandle: ...
