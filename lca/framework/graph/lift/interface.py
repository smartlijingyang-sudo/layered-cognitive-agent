"""PlanLifter — single lift interface for yaml/DTO → :class:`Plan`.

Architecture review C1 (Strong): one lift interface; parsers +
validators live behind it; :mod:`lca.framework.graph.plan_sdk`
talks only to this interface for lift concerns.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from lca.contracts.protocols.graph.plan import Plan
from lca.framework.graph.lift.executable import lift_executable_plan
from lca.framework.graph.lift.graph_spec import lift_graph_spec
from lca.framework.graph.lift.validators import validate_predicates, validate_termination


@runtime_checkable
class PlanLifter(Protocol):
    """Typed lift seam: mapping or executable DTO → :class:`Plan`."""

    def lift_graph_spec(self, spec: Mapping[str, Any]) -> Plan:
        """Lift a v2 BundleGraphSpec-shaped mapping."""
        ...

    def lift_executable_plan(self, executable: object) -> Plan:
        """Lift a production ExecutablePlan (or duck-typed equivalent)."""
        ...


class DefaultPlanLifter:
    """Production :class:`PlanLifter` — delegates to deep lift modules."""

    def lift_graph_spec(self, spec: Mapping[str, Any]) -> Plan:
        return lift_graph_spec(spec)

    def lift_executable_plan(self, executable: object) -> Plan:
        return lift_executable_plan(executable)


_DEFAULT_LIFTER = DefaultPlanLifter()


def get_plan_lifter() -> PlanLifter:
    """Return the process-default :class:`PlanLifter`."""
    return _DEFAULT_LIFTER


__all__ = [
    "DefaultPlanLifter",
    "PlanLifter",
    "get_plan_lifter",
    "lift_executable_plan",
    "lift_graph_spec",
    "validate_predicates",
    "validate_termination",
]
