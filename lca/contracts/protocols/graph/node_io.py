"""Node IO schema — typed contract for graph node data flow.

Every node declares its inputs and outputs as a :class:`NodeIOSchema`.
The graph kernel validates at the seam (``PlanLifter`` / strategy
``enter``) that ``NodeOutput.port_values`` keys are a subset of
``schema.outputs`` names and that the schema's required inputs are
satisfied by the upstream ``port_registry``.

Design constraints:

- ``extra="forbid"`` everywhere so unknown keys fail loud at Pydantic
  parse time, not silently at runtime.
- All models frozen. Strategies must not mutate input or output.
- :class:`NodeInput.require` and :class:`NodeOutput.require` raise
  :class:`NodeSchemaError` with structured context (producer node,
  consumer node, requested port) so debug never relies on grep logs.
- :class:`PortSpec.payload_type` is load-bearing for predicate lift
  validation (Task 5). ``None`` means the port is dynamic and predicates
  cannot use ``field`` (only the port value as a whole).

What's NOT here: business DTO names like ``Decision`` / ``Observation`` /
``Reflection`` — those live in :mod:`lca.contracts.models.core.execution`
and are projected onto this schema via the ACL in
:mod:`lca.cognition.wire.close_out_adapter` (PR-2).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import dataclasses

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lca.contracts.protocols.graph.ports import PortName
from lca.contracts.protocols.graph.predicate import Predicate


class NodeSchemaError(ValueError):
    """Raised when a node IO schema is violated.

    Carries the producer / consumer / port names so debug traces
    are self-describing without depending on log search.
    """


class PortSpec(BaseModel):
    """One typed port declaration on a node.

    The ``payload_type`` is load-bearing for lift-time validation of
    :class:`Predicate.field` references. When ``None``, the port is
    dynamic and predicates cannot access fields (only the port value
    as a whole). Lift validation (Task 5) rejects ``Predicate.field is not None``
    on a port with ``payload_type is None``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: PortName
    required: bool = True
    payload_type: type | None = None  # None = dynamic port, no field access


class NodeIOSchema(BaseModel):
    """Inputs and outputs a node declares to the graph kernel.

    Strategies implement :class:`lca.contracts.protocols.graph.strategy.NodeStrategy`
    and reference this schema via the ``schema`` attribute. The graph
    kernel never inspects schema names directly; it hands them to
    :class:`lca.framework.graph.port_registry.PortRegistry` to build
    :class:`NodeInput`.

    The ``terminal_predicate`` is evaluated after each visit to this node.
    If it matches, the kernel terminates the plan (no edge selection needed).
    This replaces the legacy ``terminal.commit`` outer node pattern.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    inputs: tuple[PortSpec, ...] = Field(default_factory=tuple)
    outputs: tuple[PortSpec, ...] = Field(default_factory=tuple)
    terminal_predicate: Predicate | None = None  # plan-level termination

    @model_validator(mode="after")
    def _names_unique(self) -> NodeIOSchema:
        # Uniqueness is enforced within each direction (no two
        # inputs share a name; no two outputs share a name). A
        # port that appears on both sides is intentionally
        # permitted — it represents a read+write alias (e.g. an
        # act subgraph reads ``decision`` from upstream and emits
        # a stamped ``decision`` downstream under the same name).
        seen_in: set[PortName] = set()
        for spec in self.inputs:
            if spec.name in seen_in:
                raise NodeSchemaError(f"duplicate input port name in schema: {spec.name!r}")
            seen_in.add(spec.name)
        seen_out: set[PortName] = set()
        for spec in self.outputs:
            if spec.name in seen_out:
                raise NodeSchemaError(f"duplicate output port name in schema: {spec.name!r}")
            seen_out.add(spec.name)
        return self

    def required_inputs(self) -> tuple[PortName, ...]:
        return tuple(p.name for p in self.inputs if p.required)

    def output_names(self) -> frozenset[PortName]:
        return frozenset(p.name for p in self.outputs)

    def satisfied_by(self, incoming: Mapping[PortName, Any]) -> bool:
        return all(p.name in incoming for p in self.inputs if p.required)

    def project_outputs(self, produced: Mapping[PortName, Any]) -> Mapping[PortName, Any]:
        declared = self.output_names()
        unknown = set(produced) - declared
        if unknown:
            raise NodeSchemaError(
                f"produced ports {sorted(unknown)} not declared in schema.outputs={sorted(declared)}"
            )
        return produced


class NodeInput(BaseModel):
    """Frozen input handed to a node strategy.

    Built by :class:`lca.framework.graph.port_registry.PortRegistry.build_input`
    from the registry's port store filtered by ``schema.required_inputs``.
    Strategies may call :meth:`require` to fetch a port; missing required
    ports raise :class:`NodeSchemaError` instead of returning ``None``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    port_values: Mapping[PortName, Any] = Field(default_factory=dict)
    consumer_node: str = ""

    def require(self, name: PortName) -> Any:
        if name not in self.port_values:
            raise NodeSchemaError(
                f"consumer_node={self.consumer_node!r} requires port {name!r} "
                f"but the upstream did not produce it"
            )
        return self.port_values[name]

    def get(self, name: PortName, default: Any = None) -> Any:
        return self.port_values.get(name, default)


class NodeOutput(BaseModel):
    """Frozen output produced by a node strategy.

    Keys must be a subset of the strategy's declared schema. The graph
    kernel calls :meth:`NodeIOSchema.project_outputs` to enforce this
    after the strategy returns.

    Routing decisions are now expressed through the typed ``RoutingDecision``
    port (see :mod:`lca.contracts.protocols.graph.routing`). The legacy
    ``result_kind``, ``next_hint``, and ``next_hints`` fields have been
    removed — they are replaced by the typed port store.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    port_values: Mapping[PortName, Any] = Field(default_factory=dict)
    producer_node: str = ""


__all__ = [
    "NodeInput",
    "NodeIOSchema",
    "NodeOutput",
    "NodeSchemaError",
    "PortSpec",
]