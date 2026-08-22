"""ADR-0075 最小可信内核的声明式编译、组装与执行实现。"""

from lca.harness.declarative.assembler import (
    ExecutableNode,
    ExecutablePlan,
    GraphAssembler,
    MappingRestrictedScope,
    RestrictedScope,
)
from lca.harness.declarative.compiler import (
    DeclarativePlanProjection,
    compile_declarative_projection,
)
from lca.harness.declarative.interpreter import (
    GenericPlanInterpreter,
    InMemoryJournalCommitter,
    InterpretationResult,
    PhaseVisit,
    RestrictedPhaseContext,
)

__all__ = [
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
]
