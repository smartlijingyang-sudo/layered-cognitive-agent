"""Observability compile graph — typed plan DTOs (ADR-0198).

Compile-time SSOT for event closure, projection bindings, and output artifacts.
Runtime fold/deriver code reads :class:`CompiledObservabilityPlan`; yaml lives under
``lca_kernel/events/config/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ObservabilityLayer = Literal[
    "L0_run_envelope",
    "L1_step_boundary",
    "L2_model_visible",
    "L3_evidence",
    "L4_phase_summary",
    "L5_invocation_span",
]

MergeStrategy = Literal[
    "replace",
    "replace_richer",
    "fill_empty_only",
    "deny_overwrite",
]

CompileSeverity = Literal["error", "warn", "info"]

ProjectionKind = Literal[
    "fold_reducer",
    "incremental_fold",
    "render_template",
    "metrics_reducer",
]

OutputFormat = Literal["ndjson", "json", "markdown", "dot"]


@dataclass(frozen=True, slots=True)
class CompileDiagnostic:
    """One compile-time finding; surfaced by CLI and boot validation."""

    severity: CompileSeverity
    code: str
    message: str
    path: str = ""


@dataclass(frozen=True, slots=True)
class EventClosureSpec:
    """Closure record for a single execution point (bare EP name)."""

    execution_point: str
    layer: ObservabilityLayer
    durable: bool
    producer_seam: str
    consumers: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LayerMergePolicy:
    """Global rule: source layer must not overwrite richer target layer."""

    source_layer: ObservabilityLayer
    target_layer: ObservabilityLayer
    strategy: MergeStrategy


@dataclass(frozen=True, slots=True)
class FieldExtractSpec:
    """Maps one target field to a payload path (``payload.foo``) or alternates ``a|b``."""

    target_field: str
    source: str


@dataclass(frozen=True, slots=True)
class BindingRule:
    """One fold binding: match EP → extract fields → merge into journal frame field."""

    rule_id: str
    execution_point: str
    target_field: str
    extracts: tuple[FieldExtractSpec, ...]
    merge: MergeStrategy
    precedence: int
    when_objective_kind: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectionSpec:
    """Registered projection (deriver) fed by binding rules."""

    projection_id: str
    kind: ProjectionKind
    plugin_id: str
    state_schema: str
    bindings_ref: str
    input_include: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OutputArtifactSpec:
    """Materialized run artifact derived from a projection."""

    artifact_id: str
    path_pattern: str
    format: OutputFormat
    schema: str
    source_projection: str
    durable_ssot: bool = False


@dataclass(frozen=True, slots=True)
class CompiledObservabilityPlan:
    """Frozen compile product — like CompiledRunPlan for observe-time."""

    schema_version: str
    closure_events: tuple[EventClosureSpec, ...]
    layer_policies: tuple[LayerMergePolicy, ...]
    projections: tuple[ProjectionSpec, ...]
    bindings_by_projection: dict[str, tuple[BindingRule, ...]]
    outputs: tuple[OutputArtifactSpec, ...]
    diagnostics: tuple[CompileDiagnostic, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)

    def closure_for(self, execution_point: str) -> EventClosureSpec | None:
        for spec in self.closure_events:
            if spec.execution_point == execution_point:
                return spec
        return None

    def binding_rules_for(self, projection_id: str) -> tuple[BindingRule, ...]:
        return self.bindings_by_projection.get(projection_id, ())

    def merge_for_ep(self, execution_point: str, *, projection_id: str = "journal.step_tree") -> MergeStrategy:
        rules = self.binding_rules_for(projection_id)
        matched = [r for r in rules if r.execution_point == execution_point]
        if not matched:
            return "replace"
        return max(matched, key=lambda r: r.precedence).merge


__all__ = [
    "BindingRule",
    "CompileDiagnostic",
    "CompileSeverity",
    "CompiledObservabilityPlan",
    "EventClosureSpec",
    "FieldExtractSpec",
    "LayerMergePolicy",
    "MergeStrategy",
    "ObservabilityLayer",
    "OutputArtifactSpec",
    "OutputFormat",
    "ProjectionKind",
    "ProjectionSpec",
]
