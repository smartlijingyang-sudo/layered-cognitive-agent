"""PlanCheck abstraction — base class for every plan-level boot validator.

Design pattern
==============

Each ``PlanCheck`` subclass is a **Strategy** implementing one focused
boot-time invariant. The enabled set lives in
:data:`lca_kernel.boot.plan_validation.core._PLAN_CHECKS`;
:func:`lca_kernel.boot.plan_validation.core._check_lifted_plan`
runs every registered check against the lifted :class:`Plan` and
aggregates the returned :class:`PlanLiftError` list into a single
failure so the operator sees every problem in one boot pass.

Why a class instead of a free function?
---------------------------------------

The class form costs no lines vs. a free function but gives the
operator a single, stable surface for:

- **Discovery** — :data:`lca_kernel.boot.plan_validation.core._PLAN_CHECKS`
  lists the enabled strategies; :meth:`CheckerRegistry.describe`
  prints every registered check with its id and docstring.
- **Per-check tests** — every subclass is independently importable
  and unit-testable against a hand-built :class:`Plan`, so adding a
  new invariant is one subclass + one test file.

Naming convention
-----------------

Subclass name is the human label (``TypedPortWiringCheck``); the
``check_id`` class attribute is the stable, machine-readable handle
(``"typed_port_wiring"``) used in :class:`PlanLiftError` messages
and in test parametrization.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan


class PlanCheck(ABC):
    """One plan-level boot-time invariant.

    Subclasses implement :meth:`run`. The default ``__call__``
    adapts the method to the ``(plan, *, plan_id)`` keyword-only
    shape (see ``_CheckCallable`` in
    :mod:`lca_kernel.boot.plan_validation.core`) so
    :func:`_check_lifted_plan` can iterate over a heterogeneous
    registry without special-casing each strategy.
    """

    #: Stable machine-readable id (``"typed_port_wiring"``,
    #: ``"reachability"``, etc.). Used in :class:`PlanLiftError`
    #: messages and in tests.
    check_id: str = ""

    #: Short human label for log / describe output.
    label: str = ""

    def __call__(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        return self.run(plan, plan_id=plan_id)

    @abstractmethod
    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        """Return a :class:`PlanLiftError` if the plan violates the invariant."""

    def describe(self) -> dict[str, Any]:
        """Return a structured description for ``describe()`` / introspection."""
        return {
            "id": self.check_id,
            "label": self.label,
            "doc": (self.run.__doc__ or "").strip().splitlines()[0]
            if self.run.__doc__
            else "",
        }


class CheckerRegistry:
    """Holds a set of :class:`PlanCheck` strategies.

    Acts as a thin composition root over a tuple of strategies so
    the iteration order is stable and the set can be inspected.
    The active default set is
    :data:`lca_kernel.boot.plan_validation.core._PLAN_CHECKS`.
    Tests can construct a local registry with a curated subset to
    exercise individual checks in isolation.
    """

    def __init__(self, checks: tuple[PlanCheck, ...]) -> None:
        self._checks = tuple(checks)

    def __iter__(self) -> Any:
        return iter(self._checks)

    def __len__(self) -> int:
        return len(self._checks)

    def __contains__(self, check_id: str) -> bool:
        return any(c.check_id == check_id for c in self._checks)

    def describe(self) -> list[dict[str, Any]]:
        """Return each registered check's id, label, and one-line doc."""
        return [c.describe() for c in self._checks]


__all__ = ["CheckerRegistry", "PlanCheck"]
