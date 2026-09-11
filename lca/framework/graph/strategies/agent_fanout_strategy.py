"""AgentFanoutStrategy — fan out to N agents and reduce.

The strategy sends the same :class:`AgentRequest` to each target in
``node_config['targets']``, awaits all responses (sequentially today;
async.gather swap-in is a PR-7 concern), and merges the payloads via
a host-injected reducer.

The strategy deliberately reuses :class:`AgentClient.fanout` instead
of calling :meth:`consult` N times — the production agent client may
batch, route, or short-circuit per-target.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
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

FanoutReducer = Callable[[Sequence[AgentResponse]], dict[str, Any]]


def default_fanout_reducer(responses: Iterable[AgentResponse]) -> dict[str, Any]:
    """Last-write-wins fan-in reducer. Deterministic for a given input."""
    merged: dict[str, Any] = {}
    for response in responses:
        if response.status == "ok":
            merged.update(response.payload)
    return merged


@dataclass(frozen=True, slots=True)
class AgentFanoutStrategy(NodeStrategy):
    kind: BindingKind = BindingKind.AGENT_FANOUT
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    client: AgentClient | None = None
    reducer: FanoutReducer = default_fanout_reducer

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        if self.client is None:
            raise RuntimeError(
                "AgentFanoutStrategy.execute called without client"
            )
        targets = context.node_config.get("targets") or ()
        if not isinstance(targets, (list, tuple)) or len(targets) == 0:
            raise RuntimeError(
                f"AgentFanoutStrategy at {context.node_id!r}: "
                f"node_config['targets'] must be a non-empty sequence"
            )
        request = AgentRequest(
            target_agent="*",
            intent=str(context.node_config.get("intent", "")),
            payload=dict(input.port_values),
            trace_id=str(context.node_config.get("trace_id", "")),
            timeout_s=context.node_config.get("timeout_s"),
        )
        responses = await self.client.fanout(request, targets=targets)
        merged = self.reducer(responses)
        return NodeOutput(port_values=merged, producer_node=context.node_id)


class _StubClient:
    async def consult(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            source_agent=request.target_agent,
            status="ok",
            payload={"response": f"echo:{request.target_agent}"},
        )

    async def fanout(
        self, request: AgentRequest, *, targets: Sequence[str]
    ) -> Sequence[AgentResponse]:
        return [
            AgentResponse(
                source_agent=t,
                status="ok",
                payload={"response": f"echo:{t}"},
            )
            for t in targets
        ]


register_strategy(AgentFanoutStrategy(client=_StubClient()))


__all__ = [
    "AgentFanoutStrategy",
    "FanoutReducer",
    "default_fanout_reducer",
]