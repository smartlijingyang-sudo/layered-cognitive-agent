"""Backward-compat re-export of the production interpreter.

Per the act-subgraph seam cutover (note 2026-09-11), the production
interpreter is :class:`lca.framework.graph.adapter.PlanInterpreterAdapter`.
This shim stays so existing imports of
``lca.harness.graph.execute.interpreter`` keep resolving until all
callers migrate to ``lca.framework.graph.adapter``.
"""

from __future__ import annotations

from typing import Any

_OTHER_NAMES = (
    "InterpretationResult",
    "PhaseVisit",
    "RestrictedPhaseContext",
)

__all__ = (  # noqa: F822 - lazy-loaded via __getattr__
    "InterpretationResult",
    "PhaseVisit",
    "PlanInterpreterAdapter",
    "RestrictedPhaseContext",
)


def __getattr__(name: str) -> Any:
    """Defer the framework import until the first attribute access.

    The interpreter module participates in a transitive import cycle
    (framework → harness.graph.execute → interpreter shim → framework);
    lazy attribute access breaks the cycle by ensuring the framework
    module is fully initialised before the shim reaches back into it.
    """
    if name == "PlanInterpreterAdapter":
        from lca.framework.graph.adapter import PlanInterpreterAdapter

        value = PlanInterpreterAdapter
    elif name in _OTHER_NAMES:
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
        }
        value = mapping[name]
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value
