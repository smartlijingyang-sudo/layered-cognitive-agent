"""Typed plan lift package — yaml/DTO → :class:`Plan`.

Public surface (prefer this package or :mod:`lca.framework.graph.lifter`):

- :func:`lift_graph_spec` / :func:`lift_executable_plan`
- :class:`PlanLifter` / :class:`DefaultPlanLifter`
- :func:`validate_predicates` / :func:`validate_termination`

Deep modules (parsers, validators, subgraph contract) are package-private.
"""
from lca.framework.graph.lift.executable import lift_executable_plan
from lca.framework.graph.lift.graph_spec import (
    _lift_graph_spec_inner,
    lift_graph_spec,
    lift_graph_spec_inner,
)
from lca.framework.graph.lift.interface import (
    DefaultPlanLifter,
    PlanLifter,
    get_plan_lifter,
)
from lca.framework.graph.lift.validators import (
    _validate_termination,
    validate_predicates,
    validate_termination,
)

__all__ = [
    "DefaultPlanLifter",
    "PlanLifter",
    "_lift_graph_spec_inner",
    "_validate_termination",
    "get_plan_lifter",
    "lift_executable_plan",
    "lift_graph_spec",
    "lift_graph_spec_inner",
    "validate_predicates",
    "validate_termination",
]
