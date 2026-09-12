"""Observability boot compile helper — kernel-native (replaces
``lca.harness.composition.observability_compile`` retired by the
six-phase cutover, ADR-0221 P3).

Moved out of ``lca.harness.composition`` so the kernel boot path no
longer crosses the harness→kernel layer boundary. The compiled
``CompiledObservabilityPlan`` schema is unchanged; only the call site
moved.
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.observability.compile.plan import CompiledObservabilityPlan
from lca_kernel.events.compile.compiler import ObservabilityCompiler


class ObservabilityCompileError(RuntimeError):
    """Raised when observability yaml fails compile validation at boot."""


def compile_observability_boot_plan(
    config_dir: Path | None = None,
) -> CompiledObservabilityPlan:
    """Compile observability plan; fail-loud when error diagnostics exist."""
    root = config_dir
    plan = ObservabilityCompiler.compile(root)
    errors = [d for d in plan.diagnostics if d.severity == "error"]
    if errors:
        codes = ", ".join(f"{d.code}@{d.path}" for d in errors)
        raise ObservabilityCompileError(f"observability compile plan invalid: {codes}")
    return plan


__all__ = ["ObservabilityCompileError", "compile_observability_boot_plan"]
