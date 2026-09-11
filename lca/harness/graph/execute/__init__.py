"""Graph interpretation boundary (ADR-0194 P4-G02).

Re-exports the production interpreter entry point
(:class:`lca.framework.graph.adapter.PlanInterpreterAdapter`) via lazy
attribute access so the harness ``lca.harness.graph.execute`` package
remains importable without pulling the framework kernel eagerly.
"""

from __future__ import annotations

from typing import Any

_LAZY_NAMES = (
    "InterpretationResult",
    "MAX_SUBGRAPH_DEPTH",
    "PhaseVisit",
    "PlanInterpreterAdapter",
    "RestrictedPhaseContext",
)

__all__ = list(_LAZY_NAMES)


def __getattr__(name: str) -> Any:
    """Defer the framework import until the first attribute access."""
    if name not in _LAZY_NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name == "PlanInterpreterAdapter":
        from lca.framework.graph.adapter import PlanInterpreterAdapter

        value = PlanInterpreterAdapter
    else:
        from lca.harness.declarative.execute.outcome_projection import (
            InterpretationResult,
            PhaseVisit,
        )
        from lca.harness.declarative.lifecycle.phase_context import (
            RestrictedPhaseContext,
        )

        mapping = {
            "InterpretationResult": InterpretationResult,
            "PhaseVisit": PhaseVisit,
            "RestrictedPhaseContext": RestrictedPhaseContext,
            "MAX_SUBGRAPH_DEPTH": 4,
        }
        value = mapping[name]
    globals()[name] = value
    return value
