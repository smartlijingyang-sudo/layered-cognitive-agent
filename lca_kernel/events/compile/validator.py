"""Validate CompiledObservabilityPlan (ADR-0198)."""

from __future__ import annotations

from pathlib import Path

from lca.contracts.observability.compile.plan import (
    CompileDiagnostic,
    CompiledObservabilityPlan,
    EventClosureSpec,
)
from lca_kernel.events.payloads.spine import SPINE_EXECUTION_POINTS


def _known_execution_points(closure: tuple[EventClosureSpec, ...]) -> frozenset[str]:
    return frozenset(spec.execution_point for spec in closure) | frozenset(SPINE_EXECUTION_POINTS)


def validate_compiled_plan(
    plan: CompiledObservabilityPlan,
    *,
    config_dir: Path,
) -> tuple[CompileDiagnostic, ...]:
    """Return diagnostics; errors mean plan.ok is False."""
    diagnostics: list[CompileDiagnostic] = []
    known_eps = _known_execution_points(plan.closure_events)
    closure_eps = [s.execution_point for s in plan.closure_events]
    seen_closure: set[str] = set()
    for ep in closure_eps:
        if ep in seen_closure:
            diagnostics.append(
                CompileDiagnostic(
                    severity="error",
                    code="closure.duplicate_ep",
                    message=f"execution_point {ep!r} registered twice in closure_catalog",
                    path=str(config_dir / "observability/closure_catalog.yaml"),
                )
            )
        seen_closure.add(ep)

    projection_ids = {p.projection_id for p in plan.projections}
    bindings_dir = config_dir / "projections" / "bindings"

    for projection in plan.projections:
        binding_path = config_dir / projection.bindings_ref
        if not binding_path.is_file():
            diagnostics.append(
                CompileDiagnostic(
                    severity="error",
                    code="projection.missing_bindings",
                    message=f"projection {projection.projection_id!r} bindings_ref not found",
                    path=str(binding_path),
                )
            )
        rules = plan.bindings_by_projection.get(projection.projection_id, ())
        rule_ids: set[str] = set()
        for rule in rules:
            if rule.rule_id in rule_ids:
                diagnostics.append(
                    CompileDiagnostic(
                        severity="error",
                        code="bindings.duplicate_rule_id",
                        message=f"duplicate rule id {rule.rule_id!r}",
                        path=str(binding_path),
                    )
                )
            rule_ids.add(rule.rule_id)
            if rule.execution_point not in known_eps:
                diagnostics.append(
                    CompileDiagnostic(
                        severity="warn",
                        code="bindings.unknown_ep",
                        message=(
                            f"rule {rule.rule_id!r} references EP {rule.execution_point!r} "
                            "not in closure_catalog or SPINE_EXECUTION_POINTS"
                        ),
                        path=str(binding_path),
                    )
                )

    for projection in plan.projections:
        if projection.projection_id not in plan.bindings_by_projection:
            diagnostics.append(
                CompileDiagnostic(
                    severity="warn",
                    code="projection.no_bindings_loaded",
                    message=f"no binding file loaded for projection {projection.projection_id!r}",
                    path=str(bindings_dir),
                )
            )

    special_sources = frozenset(
        {"persistence.spine", "doctor.run_manifest", "exporter.otel", "metrics.default"}
    )
    allowed_sources = projection_ids | special_sources
    for artifact in plan.outputs:
        if artifact.source_projection not in allowed_sources:
            diagnostics.append(
                CompileDiagnostic(
                    severity="error",
                    code="output.unknown_source",
                    message=(
                        f"artifact {artifact.artifact_id!r} source_projection "
                        f"{artifact.source_projection!r} not in registry"
                    ),
                    path=str(config_dir / "outputs/run_artifacts.yaml"),
                )
            )

    durable_artifacts = [a for a in plan.outputs if a.durable_ssot]
    if len(durable_artifacts) != 1:
        diagnostics.append(
            CompileDiagnostic(
                severity="error" if len(durable_artifacts) == 0 else "warn",
                code="output.durable_ssot_count",
                message=f"expected exactly one durable_ssot artifact, got {len(durable_artifacts)}",
                path=str(config_dir / "outputs/run_artifacts.yaml"),
            )
        )

    for spec in plan.closure_events:
        if spec.durable and "persistence.spine" not in spec.consumers:
            diagnostics.append(
                CompileDiagnostic(
                    severity="warn",
                    code="closure.durable_without_persistence",
                    message=(
                        f"durable EP {spec.execution_point!r} missing persistence.spine consumer"
                    ),
                    path=str(config_dir / "observability/closure_catalog.yaml"),
                )
            )

    return tuple(diagnostics)


__all__ = ["validate_compiled_plan"]
