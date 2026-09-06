"""Observability compile graph — yaml → CompiledObservabilityPlan (ADR-0198)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lca.contracts.observability.compile.plan import (
    CompileDiagnostic,
    CompiledObservabilityPlan,
)
from lca_kernel.events.compile.loader import (
    load_bindings_for_config_dir,
    load_closure_catalog,
    load_global_policies,
    load_output_artifacts,
    load_projection_registry,
)
from lca_kernel.events.compile.validator import validate_compiled_plan

_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


class ObservabilityCompiler:
    """Compile observability yaml into a frozen plan."""

    @staticmethod
    def compile(config_dir: Path | None = None) -> CompiledObservabilityPlan:
        root = Path(config_dir) if config_dir is not None else _DEFAULT_CONFIG_DIR
        load_errors: list[CompileDiagnostic] = []
        layer_policies: tuple = ()
        closure_events: tuple = ()
        projections: tuple = ()
        outputs: tuple = ()
        bindings_by_projection: dict = {}

        try:
            layer_policies = load_global_policies(root / "compile" / "global_policies.yaml")
        except ValueError as exc:
            load_errors.append(
                CompileDiagnostic(
                    severity="error",
                    code="load.global_policies",
                    message=str(exc),
                    path=str(root / "compile/global_policies.yaml"),
                )
            )

        try:
            closure_events = load_closure_catalog(root / "observability" / "closure_catalog.yaml")
        except ValueError as exc:
            load_errors.append(
                CompileDiagnostic(
                    severity="error",
                    code="load.closure_catalog",
                    message=str(exc),
                    path=str(root / "observability/closure_catalog.yaml"),
                )
            )

        try:
            projections = load_projection_registry(root / "projections" / "registry.yaml")
        except ValueError as exc:
            load_errors.append(
                CompileDiagnostic(
                    severity="error",
                    code="load.projection_registry",
                    message=str(exc),
                    path=str(root / "projections/registry.yaml"),
                )
            )

        try:
            outputs = load_output_artifacts(root / "outputs" / "run_artifacts.yaml")
        except ValueError as exc:
            load_errors.append(
                CompileDiagnostic(
                    severity="error",
                    code="load.outputs",
                    message=str(exc),
                    path=str(root / "outputs/run_artifacts.yaml"),
                )
            )

        try:
            bindings_by_projection = load_bindings_for_config_dir(root)
        except ValueError as exc:
            load_errors.append(
                CompileDiagnostic(
                    severity="error",
                    code="load.bindings",
                    message=str(exc),
                    path=str(root / "projections/bindings"),
                )
            )

        plan = CompiledObservabilityPlan(
            schema_version="lca.observability.compile/1",
            closure_events=closure_events,
            layer_policies=layer_policies,
            projections=projections,
            bindings_by_projection=bindings_by_projection,
            outputs=outputs,
            diagnostics=tuple(load_errors),
        )
        validation = validate_compiled_plan(plan, config_dir=root)
        all_diag = plan.diagnostics + validation
        return CompiledObservabilityPlan(
            schema_version=plan.schema_version,
            closure_events=plan.closure_events,
            layer_policies=plan.layer_policies,
            projections=plan.projections,
            bindings_by_projection=plan.bindings_by_projection,
            outputs=plan.outputs,
            diagnostics=all_diag,
        )


@lru_cache(maxsize=1)
def compiled_observability_plan(config_dir: str | None = None) -> CompiledObservabilityPlan:
    """Process-wide cached default plan (tests call ObservabilityCompiler.compile directly)."""
    path = Path(config_dir) if config_dir is not None else _DEFAULT_CONFIG_DIR
    return ObservabilityCompiler.compile(path)


def reset_compiled_plan_cache() -> None:
    """Test seam: clear cached plan."""
    compiled_observability_plan.cache_clear()


__all__ = [
    "ObservabilityCompiler",
    "compiled_observability_plan",
    "reset_compiled_plan_cache",
]
