"""Strategy protocol — the contract every graph node kind implements.

A strategy is a stateless object (state lives in the
:class:`StrategyContext`) that takes a :class:`NodeInput` and produces
a :class:`NodeOutput`. The kernel calls ``execute`` once per visit;
strategies never see the visit history.

This Protocol is the seam where the kernel ends and business begins.
The kernel dispatches to a strategy based on
:class:`lca.contracts.protocols.graph.binding.BindingKind`; the
strategy may freely import cognition / framework / plugins as long
as it does not mutate the kernel state directly. All state changes
flow through the :class:`StrategyContext`.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeInput, NodeIOSchema, NodeOutput
from lca.contracts.protocols.graph.plan import SubgraphReference


class StrategyContext(BaseModel):
    """Per-visit context handed to a strategy.

    Holds the run-scoped services the kernel injects (Cordis ctx,
    port registry handle, current node identity, current plan_ref).
    Strategies must not mutate ``node_id`` / ``plan_ref``; mutation
    breaks the dispatch loop. All other fields are read-only views.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_ref: str
    node_id: str
    binding_kind: BindingKind
    node_config: Mapping[str, Any]
    subgraph_ref: SubgraphReference | None = None
    chain: tuple[str, ...] = ()
    # Inner-facing port schema for subgraph nodes (first-principle
    # port-naming fix). ``None`` means outer port names coincide with
    # inner entry port names (identity translation). ``SubgraphStrategy``
    # reads this to translate outer input ports → inner input ports and
    # inner output ports → outer output ports at the subgraph seam;
    # other strategies ignore it.
    inner_io_schema: NodeIOSchema | None = None


@runtime_checkable
class NodeStrategy(Protocol):
    """The contract every graph node strategy implements.

    A strategy is stateless between visits. The kernel owns the
    visit lifecycle; the strategy only declares its kind, schema,
    and executes one input → output. Edge selection and dispatch
    decisions are kernel work, not strategy work.
    """

    kind: BindingKind
    schema: NodeIOSchema

    async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput: ...


__all__ = ["NodeStrategy", "StrategyContext"]
