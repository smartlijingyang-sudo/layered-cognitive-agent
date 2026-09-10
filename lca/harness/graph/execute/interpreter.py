"""Backward-compat re-export of :class:`GenericPlanInterpreter`.

Per review 2026-09-10 §13.10: the interpreter class itself lives in
``lca.framework.declarative.plugins.interpreter`` (where it is also
``@plugin``-registered as a Cordis DRIVER).  This module remains so
existing tests and downstream callers can keep importing
``lca.harness.graph.execute.interpreter`` until they migrate to the
framework plugin path.

Deletion point: this shim is removed together with the rest of the
think-subgraph single-engine rollout (see
``docs/specs/0194-0195-implementation-plan.md`` §P5 and ADR-0195 §2.5).
"""

from __future__ import annotations

from typing import Any

_LAZY_NAMES = (
    "GenericPlanInterpreter",
    "InMemoryJournalCommitter",
    "MAX_SUBGRAPH_DEPTH",
    "_resolve_phase_graph",
)
_OTHER_NAMES = (
    "InterpretationResult",
    "PhaseVisit",
    "RestrictedPhaseContext",
)

__all__ = (  # noqa: F822 - lazy-loaded via __getattr__
    "MAX_SUBGRAPH_DEPTH",
    "GenericPlanInterpreter",
    "InMemoryJournalCommitter",
    "InterpretationResult",
    "PhaseVisit",
    "RestrictedPhaseContext",
    "_resolve_phase_graph",
)


def __getattr__(name: str) -> Any:
    """Defer the framework import until the first attribute access.

    The interpreter module participates in a transitive import cycle
    (framework → harness.graph.execute → interpreter shim → framework);
    lazy attribute access breaks the cycle by ensuring the framework
    module is fully initialised before the shim reaches back into it.
    """
    if name in _LAZY_NAMES:
        import importlib

        module = importlib.import_module("lca.framework.declarative.plugins.interpreter")
        value = getattr(module, name)
        globals()[name] = value
        return value
    if name in _OTHER_NAMES:
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
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
