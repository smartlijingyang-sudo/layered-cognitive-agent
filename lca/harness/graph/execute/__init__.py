"""Graph interpretation boundary (ADR-0194 P4-G02).

Re-exports use lazy attribute access to break the import cycle between
``lca.framework.declarative.plugins.interpreter`` (think-subgraph
single-engine, batch 2) and the harness ``lca.harness.graph.execute``
package that owns the re-export shim.
"""

from __future__ import annotations

from typing import Any

_LAZY_NAMES = (
    "GenericPlanInterpreter",
    "InMemoryJournalCommitter",
    "InterpretationResult",
    "MAX_SUBGRAPH_DEPTH",
    "PhaseVisit",
    "RestrictedPhaseContext",
)

__all__ = list(_LAZY_NAMES)


def __getattr__(name: str) -> Any:
    """Defer the shim resolution until the first attribute access."""
    if name not in _LAZY_NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from lca.harness.graph.execute import interpreter as _interpreter

    value = getattr(_interpreter, name)
    globals()[name] = value
    return value
