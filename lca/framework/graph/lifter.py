"""PlanLifter facade — yaml / ExecutablePlan → :class:`Plan`.

Implementation lives in :mod:`lca.framework.graph.lift` (deep lift
package). This module re-exports the stable public API and the private
helpers that existing tests / strategies still import.

Prefer importing :func:`lift_graph_spec` / :class:`PlanLifter` from
``lca.framework.graph`` or ``lca.framework.graph.lift``.
"""
from __future__ import annotations

from lca.framework.graph.lift import (
    DefaultPlanLifter,
    PlanLifter,
    _lift_graph_spec_inner,
    _validate_termination,
    get_plan_lifter,
    lift_executable_plan,
    lift_graph_spec,
    validate_predicates,
)

__all__ = [
    "DefaultPlanLifter",
    "PlanLifter",
    "_lift_graph_spec_inner",
    "_validate_termination",
    "get_plan_lifter",
    "lift_executable_plan",
    "lift_graph_spec",
    "validate_predicates",
]
