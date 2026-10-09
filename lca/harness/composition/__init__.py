"""Profile compile-time composition (ADR-0195 §2.2 P4-K01)."""

from __future__ import annotations

from lca.harness.profile.plan.explain import explain_compile_plan
from lca_kernel.plan.plan_compile import (
    CompileOptions,
    PlanCompilerError,
    compile_plan,
)

__all__ = [
    "CompileOptions",
    "PlanCompilerError",
    "compile_plan",
    "explain_compile_plan",
]
