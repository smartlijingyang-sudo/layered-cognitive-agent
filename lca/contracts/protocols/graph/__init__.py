"""Graph kernel protocols (PR-1 foundation).

Per ADR-0222 (planned): one graph kernel supports business-node
orchestration, multi-agent coordination, and inner-pipeline flow
at the same fidelity. This subpackage owns the **protocols only**;
implementations land in :mod:`lca.framework.graph` (future PR-3..PR-6).

Layer rules (enforced by ``scripts/check_framework_cognition_boundary.py``,
planned PR-8):

- This subpackage may not import ``lca.framework`` or ``lca.cognition``.
- ``lca.framework`` may import from here.
- ``lca.cognition`` may import from here (business implements the
  protocols; it does not invent them).

What's in here (PR-1):

- :mod:`ports`      — re-export :data:`PortName` Literal closure.
- :mod:`node_io`    — :class:`NodeIOSchema`, :class:`PortSpec`,
                       :class:`NodeInput`, :class:`NodeOutput`.
- :mod:`binding`    — :class:`BindingKind` enum (10 entries).
- :mod:`visit`     — :class:`VisitRecord`, :class:`DispatchDecision`.
- :mod:`plan`      — :class:`Plan`, :class:`PlanNode`, :class:`PlanEdge`.
- :mod:`strategy`  — :class:`NodeStrategy` Protocol (10 binding kinds).

What's NOT in here (deferred):

- Strategy implementations (live in ``lca.framework.graph.strategies``).
- Plan lifter from yaml (lives in ``lca.framework.graph.lifter``).
- Anti-corruption adapter between PortName and cognition close-out
  fields (lives in ``lca.cognition.wire.close_out_adapter``, PR-2).
"""
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
    NodeSchemaError,
    PortSpec,
)
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode, SubgraphReference
from lca.contracts.protocols.graph.ports import PortName
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.contracts.protocols.graph.visit import DispatchDecision, VisitRecord

__all__ = [
    "BindingKind",
    "DispatchDecision",
    "NodeInput",
    "NodeIOSchema",
    "NodeOutput",
    "NodeSchemaError",
    "NodeStrategy",
    "Plan",
    "PlanEdge",
    "PlanNode",
    "PortName",
    "PortSpec",
    "StrategyContext",
    "SubgraphReference",
    "VisitRecord",
]