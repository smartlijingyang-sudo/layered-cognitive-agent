"""ADR-0075 最小可信内核的声明式编译、组装与执行实现。"""

from lca.harness.declarative.compile.assembler import (
    ExecutableNode,
    ExecutablePlan,
    GraphAssembler,
    MappingRestrictedScope,
    RestrictedScope,
)
from lca.harness.declarative.compile.compiler import (
    DeclarativePlanProjection,
    compile_declarative_projection,
)
from lca.harness.declarative.controls.approval import (
    ApprovalState,
    ApprovalStateMachine,
    ApprovalTransition,
)
from lca.harness.declarative.controls.validation import validate_control_binding_closure
from lca.harness.declarative.execute.interpreter import (
    GenericPlanInterpreter,
    InMemoryJournalCommitter,
    InterpretationResult,
    PhaseVisit,
    RestrictedPhaseContext,
)

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
