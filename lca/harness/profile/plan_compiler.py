# COMPAT(owner: ADR-0195 P4-K01, from: lca.harness.profile.plan_compiler,
# to: lca.harness.composition.plan_compiler,
# delete_when: rg 'harness\.profile\.plan_compiler' lca/ tests/ scripts/ = 0,
# forbidden_new_usage: true)
"""Deprecated shim — use :mod:`lca.harness.composition.plan_compiler`."""

from __future__ import annotations

import warnings

from lca.harness.composition.plan_compiler import (
    CompileOptions,
    PlanCompilerError,
    compile_plan,
    explain_compile_plan,
)

warnings.warn(
    "lca.harness.profile.plan_compiler is deprecated, use lca.harness.composition.plan_compiler",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "CompileOptions",
    "PlanCompilerError",
    "compile_plan",
    "explain_compile_plan",
]
