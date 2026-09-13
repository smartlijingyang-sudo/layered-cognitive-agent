"""ADR-0075 declarative compile / controls / lifecycle surface.

Production execution walks v2 ``PlanInterpreter``
(``lca.framework.graph.interpreter``) — the v0 ``GraphAssembler`` path was
deleted in ADR-0221 P3 (commit 63a68a4d). This package no longer exports
``GraphAssembler`` / ``ExecutablePlan`` / ``MappingRestrictedScope``.

Importing ``GraphAssembler`` from here raises ``AttributeError`` so
production and tests fail loud instead of silently reconstituting a v1 path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:

    from lca.harness.declarative.controls.approval import (
        ApprovalState,
        ApprovalStateMachine,
        ApprovalTransition,
    )
    from lca.harness.declarative.controls.validation import validate_control_binding_closure
    from lca.harness.declarative.lifecycle.phase_context import RestrictedPhaseContext

__all__ = [
    "ApprovalState",
    "ApprovalStateMachine",
    "ApprovalTransition",

    "RestrictedPhaseContext",
    "validate_control_binding_closure",
]

_RETIRED_V1 = frozenset(
    {
        "GraphAssembler",
        "ExecutableNode",
        "ExecutablePlan",
        "MappingRestrictedScope",
        "RestrictedScope",
        "InterpretationResult",
        "PhaseVisit",
        "DeclarativePlanProjection",
        "compile_declarative_projection",
    }
)


def __getattr__(name: str) -> Any:
    if name in {
        "ApprovalState",
        "ApprovalStateMachine",
        "ApprovalTransition",
    }:
        from lca.harness.declarative.controls import approval as _approval

        return getattr(_approval, name)
    if name == "validate_control_binding_closure":
        from lca.harness.declarative.controls.validation import validate_control_binding_closure

        return validate_control_binding_closure
    if name == "RestrictedPhaseContext":
        from lca.harness.declarative.lifecycle.phase_context import (
            RestrictedPhaseContext,
        )

        return RestrictedPhaseContext
    if name in _RETIRED_V1:
        raise AttributeError(
            f"lca.harness.declarative.{name} was retired with the v0 GraphAssembler "
            f"path (ADR-0221 P3). Production walks PlanInterpreter only; "
            f"delete-when ≤ eng/retire-v1-reasoner-sandbox. "
            f"Import PlanInterpreter from lca.framework.graph.interpreter instead."
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
