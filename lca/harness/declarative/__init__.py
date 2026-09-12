"""ADR-0075 最小可信内核的声明式编译、组装与执行实现。

公开符号 lazy 导出，避免 ``import lca.harness.graph.*`` 时 eager 拉全链。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lca.harness.declarative.compile.assembler.assembler import (
        ExecutableNode,
        ExecutablePlan,
        GraphAssembler,
        MappingRestrictedScope,
        RestrictedScope,
    )
    from lca.harness.declarative.controls.approval import (
        ApprovalState,
        ApprovalStateMachine,
        ApprovalTransition,
    )
    from lca.harness.declarative.controls.validation import validate_control_binding_closure
    from lca.harness.declarative.execute.outcome_projection import (
        InterpretationResult,
        PhaseVisit,
    )
    from lca.harness.declarative.lifecycle.phase_context import RestrictedPhaseContext

__all__ = [
    "ApprovalState",
    "ApprovalStateMachine",
    "ApprovalTransition",
    "ExecutableNode",
    "ExecutablePlan",
    "GraphAssembler",
    "InterpretationResult",
    "MappingRestrictedScope",
    "PhaseVisit",
    "RestrictedPhaseContext",
    "RestrictedScope",
    "validate_control_binding_closure",
]


def __getattr__(name: str) -> Any:
    if name in {
        "ExecutableNode",
        "ExecutablePlan",
        "GraphAssembler",
        "MappingRestrictedScope",
        "RestrictedScope",
    }:
        from lca.harness.declarative.compile import assembler as _assembler

        return getattr(_assembler, name)
    if name in {"ApprovalState", "ApprovalStateMachine", "ApprovalTransition"}:
        from lca.harness.declarative.controls import approval as _approval

        return getattr(_approval, name)
    if name == "validate_control_binding_closure":
        from lca.harness.declarative.controls.validation import validate_control_binding_closure

        return validate_control_binding_closure
    if name in {
        "InterpretationResult",
        "PhaseVisit",
        "RestrictedPhaseContext",
    }:
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
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
