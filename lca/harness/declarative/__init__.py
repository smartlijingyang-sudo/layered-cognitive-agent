"""ADR-0075 最小可信内核的声明式编译、组装与执行实现。

公开符号 lazy 导出，避免 ``import lca.harness.declarative.graph.*`` 时 eager 拉全链。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ApprovalState",
    "ApprovalStateMachine",
    "ApprovalTransition",
    "DeclarativePlanProjection",
    "ExecutableNode",
    "ExecutablePlan",
    "GenericPlanInterpreter",
    "GraphAssembler",
    "InMemoryJournalCommitter",
    "InterpretationResult",
    "MappingRestrictedScope",
    "PhaseVisit",
    "RestrictedPhaseContext",
    "RestrictedScope",
    "compile_declarative_projection",
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
    if name in {"DeclarativePlanProjection", "compile_declarative_projection"}:
        from lca.harness.declarative.compile import compiler as _compiler

        return getattr(_compiler, name)
    if name in {"ApprovalState", "ApprovalStateMachine", "ApprovalTransition"}:
        from lca.harness.declarative.controls import approval as _approval

        return getattr(_approval, name)
    if name == "validate_control_binding_closure":
        from lca.harness.declarative.controls.validation import validate_control_binding_closure

        return validate_control_binding_closure
    if name in {
        "GenericPlanInterpreter",
        "InMemoryJournalCommitter",
        "InterpretationResult",
        "PhaseVisit",
        "RestrictedPhaseContext",
    }:
        from lca.harness.graph.execute import interpreter as _interpreter

        return getattr(_interpreter, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
