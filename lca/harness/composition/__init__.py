"""Profile compile-time composition (ADR-0195 §2.2 P4-K01)."""

from __future__ import annotations

from lca.harness.composition.boot_compile import compile_profile_boot_products
from lca.harness.composition.plan_compiler import (
    CompileOptions,
    PlanCompilerError,
    compile_plan,
    explain_compile_plan,
)

__all__ = [
    "CompileOptions",
    "PlanCompilerError",
    "compile_plan",
    "compile_profile_boot_products",
    "explain_compile_plan",
]
