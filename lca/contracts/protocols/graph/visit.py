"""Visit trace record — the typed SSOT for graph execution history.

The kernel emits one :class:`VisitRecord` per node visit. Production
deployments funnel these into the journal / spine via the existing
observer port. Tests assert against literal values.

``sub_call_chain`` records the recursion path for nested subgraphs:
the outer plan's plan_ref is the first element, the inner plan's
plan_ref is appended on each :class:`lca.contracts.protocols.graph.binding.BindingKind.SUBGRAPH`
visit. ``MAX_SUBGRAPH_DEPTH = 4`` is enforced at strategy dispatch.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.ports import PortName


class DispatchDecision(BaseModel):
    """What the kernel decided after one node visit.

    ``NEXT`` advances traversal to ``next_node``. ``TERMINAL`` ends
    the plan. ``SUBGRAPH`` advances with a nested plan_ref pushed
    onto the chain. ``FAILED`` halts with the captured error.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str  # "next" | "terminal" | "subgraph" | "failed"
    next_node: str | None = None
    subgraph_plan_ref: str | None = None
    subgraph_entry: str | None = None
    error: str | None = None


class VisitRecord(BaseModel):
    """One node visit — the SSOT for graph execution trace.

    Every :class:`lca.contracts.protocols.graph.strategy.NodeStrategy.execute`
    produces one of these via the kernel. Tests pin literal values;
    observability layers emit them through the existing
    ``phase_graph.node.start/end`` channels.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_ref: str
    node_id: str
    binding_kind: BindingKind
    inputs: Mapping[PortName, Any] = {}
    outputs: Mapping[PortName, Any] = {}
    dispatch: DispatchDecision
    sub_call_chain: tuple[str, ...] = ()
    error: str | None = None


__all__ = ["DispatchDecision", "VisitRecord"]