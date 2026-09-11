"""AgentClient — the single seam the framework uses to talk to agents.

The framework graph kernel calls :meth:`AgentClient.consult` to ask
one agent for a decision / observation, or :meth:`AgentClient.fanout`
to dispatch a request to N agents in parallel and gather responses.

The protocol is async-only and accepts a typed :class:`AgentRequest`.
The :class:`AgentResponse` carries a single typed payload plus a
``status`` field so the kernel can decide TERMINATE / NEXT / FAILED
without inspecting business DTOs.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols.graph.ports import PortName


class AgentRequest(BaseModel):
    """Typed envelope the kernel sends to an agent.

    ``payload`` carries the upstream port_values (typed dict). The
    agent adapter unwraps them into the agent's native types via the
    cognition close-out adapter.
    """

    model_config = ConfigDict(extra="forbid")

    target_agent: str
    intent: str
    payload: dict[PortName, Any] = {}
    trace_id: str = ""
    timeout_s: float | None = None


class AgentResponse(BaseModel):
    """Typed envelope the kernel receives from an agent."""

    model_config = ConfigDict(extra="forbid")

    source_agent: str
    status: str  # "ok" | "failed" | "timeout"
    payload: dict[PortName, Any] = {}
    error: str | None = None


@runtime_checkable
class AgentClient(Protocol):
    """The single seam the framework uses to consult agents.

    Implementations live in cognition (the ACL). Production
    implementation calls the existing team / collaboration plugins.
    """

    async def consult(self, request: AgentRequest) -> AgentResponse: ...

    async def fanout(
        self, request: AgentRequest, *, targets: Sequence[str]
    ) -> Sequence[AgentResponse]: ...


__all__ = ["AgentClient", "AgentRequest", "AgentResponse"]