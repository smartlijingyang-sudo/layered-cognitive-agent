"""Plan 编译(K2)。

合并自 :mod:`lca.harness.profile.plan_compiler` 与
:mod:`lca.harness.profile.capability_plan_resolver`,统一由
:func:`compile_run_plan` 导出。ADR-0115 决定 1 K2。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.harness.profile.capability_plan_resolver import (
    CapabilityPlanOptions,
    CapabilityPlanResolveError,
    project_capability_plan,
)
from lca.harness.profile.plan_compiler import (
    CompileOptions,
    PlanCompilerError,
    compile_plan,
)

if TYPE_CHECKING:
    from lca.harness.profile.resolve import ResolvedProfile


def compile_run_plan(
    resolved: ResolvedProfile,
    *,
    options: CompileOptions | None = None,
) -> object:
    """公共 API 入口(同 :func:`lca.harness.profile.plan_compiler.compile_plan`).

    命名遵循 ADR-0106 §8.1 函数前缀表(``compile_*``);保留旧名 ``compile_plan``
    作为 deprecated alias 由 compat 层转发。
    """
    return compile_plan(resolved, options=options)


__all__ = [
    "CapabilityPlanOptions",
    "CapabilityPlanResolveError",
    "CompileOptions",
    "PlanCompilerError",
    "compile_run_plan",
    "project_capability_plan",
]
