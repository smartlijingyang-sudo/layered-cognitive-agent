"""Plan DTOs — pure topology, no business semantics.

A :class:`Plan` is a directed graph with typed ports, edge predicates
(DSL via ``when``), and optional nested :class:`SubgraphReference`s.
The kernel never inspects field names; it reads only the topology
and the typed :class:`lca.contracts.protocols.graph.node_io.NodeIOSchema`
references declared on each node.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeIOSchema
from lca.contracts.protocols.graph.ports import PortName


class SubgraphReference(BaseModel):
    """Pointer from one node to another plan.

    Mirrors the legacy ``SubgraphReference`` shape in
    :mod:`lca.contracts.protocols.declarative.declarative_1.declarative_graph`
    for forward compatibility. Field names and semantics are identical;
    importing from here does not break existing yaml or callers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_ref: str
    entry_node: str
    binding_edge: str
    return_on: str = "next"


class PlanNode(BaseModel):
    """One node in a plan graph.

    ``config`` is opaque to the kernel — strategies read what they
    declared in their own schema. The kernel passes the config mapping
    verbatim via :class:`lca.contracts.protocols.graph.strategy.StrategyContext`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    binding: BindingKind
    io_schema: NodeIOSchema = Field(default_factory=NodeIOSchema)
    config: Mapping[str, Any] = Field(default_factory=dict)
    max_visits: int = 1
    terminal: bool = False
    entry: bool = False
    subgraph_ref: SubgraphReference | None = None

    @model_validator(mode="after")
    def _max_visits_positive(self) -> "PlanNode":
        if self.max_visits <= 0:
            raise ValueError(f"node {self.id!r}: max_visits must be > 0, got {self.max_visits}")
        return self


class PlanEdge(BaseModel):
    """One directed edge in a plan graph.

    ``when`` is a DSL predicate; the existing
    :func:`lca.harness.graph.predicate.evaluate_restricted_predicate`
    is reused unchanged. ``subgraph_ref`` on an edge triggers the
    same nested-execution path as :attr:`PlanNode.subgraph_ref`,
    but keyed off the edge instead of the source node.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    target: str
    when: str = "true"
    subgraph_ref: SubgraphReference | None = None


class Plan(BaseModel):
    """A complete plan graph.

    Exactly one node must have ``entry: True``. Validation errors
    surface at parse time, never at runtime.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    nodes: tuple[PlanNode, ...]
    edges: tuple[PlanEdge, ...] = ()
    approval_resume_node: str | None = None
    declared_inputs: tuple[PortName, ...] = ()

    @model_validator(mode="after")
    def _one_entry(self) -> "Plan":
        entries = [n.id for n in self.nodes if n.entry]
        if len(self.nodes) > 0 and len(entries) != 1:
            raise ValueError(
                f"plan {self.id!r}: exactly one entry node required, got {len(entries)}"
            )
        node_ids = {n.id for n in self.nodes}
        for edge in self.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(
                    f"plan {self.id!r}: edge {edge.source!r} → {edge.target!r} "
                    f"references unknown node"
                )
        return self

    def node(self, node_id: str) -> PlanNode:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"plan {self.id!r}: no node {node_id!r}")

    def outgoing(self, node_id: str) -> tuple[PlanEdge, ...]:
        return tuple(e for e in self.edges if e.source == node_id)


__all__ = ["Plan", "PlanEdge", "PlanNode", "SubgraphReference"]