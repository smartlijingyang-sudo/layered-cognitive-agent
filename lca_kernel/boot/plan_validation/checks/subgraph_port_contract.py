"""Subgraph port contract check.

When an outer plan delegates to a subgraph **without** declaring
``declared_inputs``/``declared_outputs`` on the subgraph node, the
lifter falls back to identity translation: the outer kernel reads
the subgraph entry's :class:`NodeIOSchema` (stored as
``inner_io_schema``) and forwards ports by name.

If the inner entry declares neither inputs nor outputs, the outer
kernel sees an empty port set and the subgraph becomes a black box:
downstream nodes can never receive values from it, and it can never
receive values from upstream. This silent drift is only caught at
runtime when a port lookup fails deep inside
:class:`SubgraphStrategy`. This check surfaces the problem at boot
time.

Scope
-----

Only subgraph delegate nodes (``subgraph_ref is not None``) are
inspected. Nodes with a populated ``inner_io_schema`` (at least one
input or one output) pass; nodes with an entirely empty
``inner_io_schema`` fail. Nodes with ``inner_io_schema is None`` are
skipped — that case is already caught by the lifter's
``_require_subgraph_plan_exists`` before the check registry runs.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class SubgraphPortContractCheck(PlanCheck):
    """Reject subgraph delegates whose inner schema is entirely empty.

    An empty ``inner_io_schema`` (no inputs, no outputs) means the
    outer kernel has no ports to forward across the subgraph seam.
    The fix is either to declare ports on the inner entry node or
    to declare ``declared_inputs``/``declared_outputs`` on the outer
    YAML so the lifter can build a non-trivial translation.
    """

    check_id = "subgraph_port_contract"
    label = "Subgraph port contract (outer ↔ inner name alignment)"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        for node in plan.nodes:
            if node.subgraph_ref is None:
                continue
            inner = node.inner_io_schema
            if inner is None:
                # lifter's _require_subgraph_plan_exists already
                # rejected this plan before the check registry runs
                continue
            if inner.outputs or inner.inputs:
                continue
            return PlanLiftError(
                f"plan {plan_id!r}: subgraph node {node.id!r} has "
                f"empty inner_io_schema (no inputs, no outputs); "
                f"the subgraph will be a black box to the outer "
                f"kernel. Add declared_inputs/declared_outputs to "
                f"the outer yaml, or fix the inner plan so the "
                f"entry node declares its ports.",
                plan_id=plan_id,
                node_id=node.id,
            )
        return None


__all__ = ["SubgraphPortContractCheck"]
