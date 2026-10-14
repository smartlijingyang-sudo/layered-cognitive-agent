"""Typed-port wiring check.

Reject edges whose target expects a port no predecessor produces.

The lifter validates single-edge predicate ports (:mod:`lifter`'s
:func:`validate_predicates`) but does not run a typed-port
reachability check across the plan — :class:`NodeIOSchema.required_inputs`
is satisfied lazily by :class:`PortRegistry` at runtime, so a
typo'd required port only blows up when the executor actually
walks that node. This check computes the predecessor output set
per node and rejects every missing-port case at boot time.

Entry-node inputs are out of scope: the entry's inputs are
supplied by the **outer caller** (parent plan via
:class:`SubgraphStrategy` forwarding, or the top-level kernel).
Computing "available" for an entry node would require caller-side
context that the boot-time validator doesn't have.

Subgraph delegate nodes (``subgraph_ref`` wired) are also out of
scope: their inputs are forwarded by the surrounding caller via
:class:`SubgraphStrategy`, not by an in-plan predecessor. The
kernel reads them from the registry when the subgraph is entered,
so a missing predecessor in the enclosing plan does not indicate
a real wiring fault.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan
from lca_kernel.boot.plan_validation.typed_ports import _check_typed_port_wiring

from .base import PlanCheck


class TypedPortWiringCheck(PlanCheck):
    """Plan-level typed-port wiring: edge target's required inputs must
    be produced by some reachable predecessor."""

    check_id = "typed_port_wiring"
    label = "Typed-port wiring (required inputs from predecessor)"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        return _check_typed_port_wiring(plan, plan_id=plan_id)


__all__ = ["TypedPortWiringCheck"]
