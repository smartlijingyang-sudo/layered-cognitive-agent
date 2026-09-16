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
from lca.contracts.protocols.graph.predicate import Predicate


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
    terminal: bool = False
    entry: bool = False
    subgraph_ref: SubgraphReference | None = None
    # Inner-facing schema for subgraph nodes (ADR-0217 §3.3.3 +
    # first-principle port-naming fix). When the YAML declares
    # ``declared_inputs``/``declared_outputs`` that differ from the
    # inner entry's ``inputs``/``outputs``, ``io_schema`` carries the
    # outer-facing names (YAML) and ``inner_io_schema`` carries the
    # inner entry's names. :class:`SubgraphStrategy` uses both to
    # translate port values across the seam. ``None`` for non-subgraph
    # nodes and for legacy plans whose outer/inner names coincide.
    inner_io_schema: NodeIOSchema | None = None

    # ADR-0225: per-node ``max_visits`` field removed. Termination is
    # now solely via ``Decision(action_type=respond)``, ``should_terminate``
    # from act.observe, ``AgentState.budget`` (max_steps / max_wall_clock /
    # max_tokens), and explicit ``terminal_predicate`` matches on node IO
    # schemas. The kernel never enforces a per-node visit ceiling.


class EdgeLoopObligation(BaseModel):
    """Compile-time loop / budget obligation attached to a control edge.

    Mirrors legacy :class:`LoopGuard` semantics (ADR-0075 recovery /
    ADR-0225 edge budgets) without reintroducing per-node
    ``max_visits``. Present on re-entry edges (e.g. reflect→think
    ``admit_recovery``) so boot validation can fail loud when the
    bound is missing. Runtime enforcement remains via
    ``AgentState.budget`` / guard-stack; this field is the ControlPlan
    obligation SSOT.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    max_iterations: int = Field(default=1, alias="maxIterations", gt=0)
    budget: str = "run.steps"
    terminal_predicate: Predicate | None = Field(
        default=None, alias="terminalPredicate"
    )


class PlanEdge(BaseModel):
    """One directed edge in a plan graph.

    ``when`` is a typed :class:`Predicate` (structured, lift-validated).
    ``None`` means "always true" — the edge fires unconditionally.

    D4 cutover: string DSL ``when`` fields have been deleted. Every edge
    carries a structured :class:`Predicate` or ``None``.
    ``subgraph_ref`` on an edge triggers the same nested-execution path
    as :attr:`PlanNode.subgraph_ref`, but keyed off the edge instead of
    the source node.

    ``loop`` is an optional edge obligation (maxIterations + budget) for
    bounded re-entry. Missing loop on critical recovery edges fails
    compile (M1 outer edge SSOT).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    target: str
    when: Predicate | None = None
    subgraph_ref: SubgraphReference | None = None
    loop: EdgeLoopObligation | None = None


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
    def _one_entry(self) -> Plan:
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


__all__ = ["EdgeLoopObligation", "Plan", "PlanEdge", "PlanNode", "SubgraphReference"]
