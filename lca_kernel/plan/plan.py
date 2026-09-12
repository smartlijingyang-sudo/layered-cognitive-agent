"""Plan 编译(K2) — v2 kernel-native, ADR-0221 P3.

The v2 plan compiler emits ``CompiledRunPlan`` without the
``phase_graph`` / ``phase_bindings`` regions that v1 used to feed
``GraphAssembler``. The runtime builds its executable plan directly
from ``PlanInterpreter`` + NodeExecutor subgraphs at boot.

This module is the kernel-side public entry point; it re-exports
``compile_plan`` from :mod:`lca_kernel.plan.plan_compile` so existing
imports (``from lca_kernel.plan.plan import compile_run_plan``) keep
working.
"""

from __future__ import annotations

from lca_kernel.plan.plan_compile import (
    COMPILED_RUN_PLAN_VERSION,
    CompileOptions,
    PlanCompilerError,
    compile_plan,
)


def compile_run_plan(
    resolved,
    *,
    options: CompileOptions | None = None,
) -> object:
    """公共 API 入口(同 :func:`compile_plan`)."""
    return compile_plan(resolved, options=options)


__all__ = [
    "COMPILED_RUN_PLAN_VERSION",
    "CompileOptions",
    "PlanCompilerError",
    "compile_run_plan",
]
