"""AgentConsultStrategy — ask one agent, await response.

The strategy sends a single :class:`AgentRequest` to the agent named
in ``node_config['target_agent']``, awaits the typed
:class:`AgentResponse`, and emits the response payload on the
declared output ports.

On status="failed" or status="timeout", the strategy raises so the
kernel can route to a terminal node via :class:`TerminateStrategy`.
On status="ok", the response payload is forwarded as ``NodeOutput``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.agent.client import (
    AgentClient,
    AgentRequest,
    AgentResponse,
)
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.framework.graph.strategy_registry import register_strategy


@dataclass(frozen=True, slots=True)
class AgentConsultStrategy(NodeStrategy):
    kind: BindingKind = BindingKind.AGENT_CONSULT
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    client: AgentClient | None = None

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        if self.client is None:
            raise RuntimeError(
                "AgentConsultStrategy.execute called without client"
            )
        target = str(context.node_config.get("target_agent", ""))
        if not target:
            raise RuntimeError(
                f"AgentConsultStrategy at {context.node_id!r}: "
                f"node_config['target_agent'] must be set"
            )
        request = AgentRequest(
            target_agent=target,
            intent=str(context.node_config.get("intent", "")),
            payload=dict(input.port_values),
            trace_id=str(context.node_config.get("trace_id", "")),
            timeout_s=context.node_config.get("timeout_s"),
        )
        response: AgentResponse = await self.client.consult(request)
        if response.status != "ok":
            raise RuntimeError(
                f"agent {target!r} returned status={response.status!r}: {response.error}"
            )
        return NodeOutput(
            port_values=dict(response.payload),
            producer_node=context.node_id,
        )


class _StubClient:
    async def consult(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            source_agent=request.target_agent,
            status="ok",
            payload={"response": f"echo:{request.target_agent}"},
        )

    async def fanout(self, request: AgentRequest, *, targets: Any) -> Any:
        return [
            AgentResponse(
                source_agent=t,
                status="ok",
                payload={"response": f"echo:{t}"},
            )
            for t in targets
        ]


register_strategy(AgentConsultStrategy(client=_StubClient()))


__all__ = ["AgentConsultStrategy"]