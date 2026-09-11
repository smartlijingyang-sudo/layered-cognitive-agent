"""AgentClientAdapter — production AgentClient implementation.

The framework calls :class:`lca.contracts.protocols.agent.client.AgentClient`.
This adapter is the cognition-side implementation that routes the
call into the existing team / collaboration / blackboard machinery.

The adapter is intentionally thin: it knows that ``consult`` maps to
``RoleInvoker.consult`` (single-target) and ``fanout`` maps to
``Blackboard.dispatch_many``. Real wiring happens in
:class:`lca.plugins.collaboration.team_1.team_seam_seam` /
``team_communication_seam``; the adapter delegates to a host-injected
``executor`` closure so the tests stay decoupled from the plugin
machinery.

Default behavior: a stub that echoes the target agent. Production
wiring replaces ``executor`` with the actual team machinery at boot.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.agent.client import (
    AgentClient,
    AgentRequest,
    AgentResponse,
)
from lca.cognition.wire.close_out_adapter import CloseOutAdapter


AgentExecutor = Any  # callable(request) -> response; typed by host


@dataclass(frozen=True, slots=True)
class AgentClientAdapter:
    """Default :class:`AgentClient` implementation.

    ``executor`` is the host-injected closure that actually contacts
    the target agent(s). Tests inject a stub; production injects the
    team / collaboration seam.

    ``close_out`` projects the agent's response payload (a typed
    :class:`PhaseOutput`-like object) onto the framework's port
    names. This is the single seam where the framework's port names
    meet the cognition close-out registry.
    """

    executor: AgentExecutor | None = None
    close_out: CloseOutAdapter = field(default_factory=CloseOutAdapter)

    async def consult(self, request: AgentRequest) -> AgentResponse:
        if self.executor is None:
            return _stub_consult(request)
        raw = await self.executor(request)
        return _to_response(request.target_agent, raw, self.close_out)

    async def fanout(
        self, request: AgentRequest, *, targets: Sequence[str]
    ) -> Sequence[AgentResponse]:
        out: list[AgentResponse] = []
        for target in targets:
            sub_request = AgentRequest(
                target_agent=target,
                intent=request.intent,
                payload=request.payload,
                trace_id=request.trace_id,
                timeout_s=request.timeout_s,
            )
            if self.executor is None:
                out.append(_stub_consult(sub_request))
            else:
                raw = await self.executor(sub_request)
                out.append(_to_response(target, raw, self.close_out))
        return out


def _stub_consult(request: AgentRequest) -> AgentResponse:
    """Default stub; returns an echo response."""
    return AgentResponse(
        source_agent=request.target_agent,
        status="ok",
        payload={"response": f"echo:{request.target_agent}"},
    )


def _to_response(
    source: str,
    raw: Any,
    adapter: CloseOutAdapter,
) -> AgentResponse:
    """Project a raw agent response into the framework's port shape.

    The host returns a typed payload (PhaseOutput / dataclass /
    dict). The adapter uses ``close_out.project`` when the payload is
    a mapping of PhaseOutput-like objects, else treats it as a plain
    port_values dict.
    """
    if raw is None:
        return AgentResponse(source_agent=source, status="failed", error="empty response")
    if isinstance(raw, AgentResponse):
        return raw
    if isinstance(raw, Mapping):
        return AgentResponse(
            source_agent=source,
            status="ok",
            payload=dict(raw),
        )
    return AgentResponse(
        source_agent=source,
        status="ok",
        payload={"response": raw},
    )


__all__ = ["AgentClientAdapter", "AgentExecutor"]