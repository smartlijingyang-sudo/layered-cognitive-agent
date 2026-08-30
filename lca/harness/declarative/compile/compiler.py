"""ADR-0075 的 PlanCompiler 编译 pass。

该 pass 只把已解析的 Profile 与显式 PluginSpec 变成不可变计划数据；它不导入
具体执行器、不调用 factory，也不在运行时补齐任何 binding。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from lca.contracts.protocols.declarative.declarative_common import (
    DECLARATIVE_PLAN_VERSION,
    ContributionRole,
    RelationType,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_graph import (
    ActionAuthorityPlan,
    CapabilityBinding,
    CognitivePhaseGraphPlan,
    ControlEntry,
    EffectPolicyPlan,
    PhaseBinding,
    PlanProvenance,
    ReplacementDecision,
    ValidationReport,
)
from lca.contracts.protocols.declarative.declarative_plugin import CapabilityDeclaration, PluginSpec
from lca.harness.declarative.compile.action_authority import compile_action_authority
from lca.harness.declarative.compile.effect_policy import compile_effect_policy
from lca.harness.declarative.controls.validation import (
    PhaseGraphValidator,
    PluginSpecValidator,
    validate_control_binding_closure,
)
from lca.harness.declarative.graph.phase_graph_compiler import compile_phase_graph_projection
from lca.harness.profile.projection import ResolvedProfileProjection
from lca.harness.profile.resolve import ResolvedProfile


@dataclass(frozen=True, slots=True)
class DeclarativePlanProjection:
    """将被嵌入 ``CompiledRunPlan v2`` 的 ADR-0075 数据区域。"""

    schema_version: str
    plugin_specs: tuple[PluginSpec, ...]
    capability_bindings: tuple[CapabilityBinding, ...]
    phase_graph: CognitivePhaseGraphPlan
    phase_bindings: tuple[PhaseBinding, ...]
    control_entries: tuple[ControlEntry, ...]
    replacement_map: tuple[ReplacementDecision, ...]
    effect_policy: EffectPolicyPlan
    action_authority: ActionAuthorityPlan
    provenance: PlanProvenance
    validation_report: ValidationReport


def compile_declarative_projection(
    resolved: ResolvedProfile,
    *,
    task_contract: str = "",
    environment: str = "",
    actor_grant: tuple[str, ...] = (),
    include_disabled: bool = False,
    projection: ResolvedProfileProjection | None = None,
) -> DeclarativePlanProjection:
    """编译完整的声明式计划区域。

    每个启用插件必须提供原生 ``PluginSpec``。编译器只把已声明的类型契约
    合并为计划数据，不从旧 decorator 字段推断 phase、relation 或 effect 语义。
    """

    profile = ResolvedProfileProjection.reuse_or_build(
        resolved,
        include_disabled=include_disabled,
        projection=projection,
    )
    specs = profile.require_native_plugin_specs()
    spec_report = PluginSpecValidator().validate(specs)
    active_specs, replacements = _resolve_replacements(specs)
    bindings = _compile_capability_bindings(active_specs, resolved)
    graph, phase_bindings = _compile_phase_projection(active_specs)
    controls = _compile_control_projection(phase_bindings)
    effect_policy = _compile_effect_projection(active_specs)
    action_authority = _compile_action_authority_projection(
        active_specs, task_contract=task_contract
    )
    provenance = _build_provenance(
        resolved,
        active_specs=active_specs,
        task_contract=task_contract,
        environment=environment,
        actor_grant=actor_grant,
    )
    report = _build_validation_report(
        specs=active_specs,
        graph=graph,
        phase_bindings=phase_bindings,
        effect_policy=effect_policy,
        controls=controls,
        spec_report=spec_report,
    )
    return DeclarativePlanProjection(
        schema_version=DECLARATIVE_PLAN_VERSION,
        plugin_specs=active_specs,
        capability_bindings=bindings,
        phase_graph=graph,
        phase_bindings=phase_bindings,
        control_entries=controls,
        replacement_map=replacements,
        effect_policy=effect_policy,
        action_authority=action_authority,
        provenance=provenance,
        validation_report=report,
    )


def _build_validation_report(
    *,
    specs: tuple[PluginSpec, ...],
    graph: CognitivePhaseGraphPlan,
    phase_bindings: tuple[PhaseBinding, ...],
    effect_policy: EffectPolicyPlan,
    controls: tuple[ControlEntry, ...],
    spec_report: ValidationReport,
) -> ValidationReport:
    """Combine compiler pass reports without exposing pass ordering to callers."""
    graph_report = PhaseGraphValidator().validate(graph, phase_bindings, specs, effect_policy)
    control_report = validate_control_binding_closure(specs, phase_bindings, controls)
    return ValidationReport(spec_report.issues + graph_report.issues + control_report.issues)


def _compile_action_authority_projection(
    specs: tuple[PluginSpec, ...], *, task_contract: str
) -> ActionAuthorityPlan:
    """Project action grants through the dedicated authorization seam."""
    return compile_action_authority(specs, task_contract=task_contract)


def _compile_effect_projection(
    specs: tuple[PluginSpec, ...],
) -> EffectPolicyPlan:
    """Project effect governance through a dedicated control-plane seam."""
    return compile_effect_policy(specs)


def _compile_control_projection(
    phase_bindings: tuple[PhaseBinding, ...],
) -> tuple[ControlEntry, ...]:
    """Project control contributions through one dedicated control-plane seam."""
    return _compile_control_entries(phase_bindings)


def _compile_phase_projection(
    specs: tuple[PluginSpec, ...],
) -> tuple[CognitivePhaseGraphPlan, tuple[PhaseBinding, ...]]:
    """Expose only the graph facts needed by the outer projection compiler."""
    projection = compile_phase_graph_projection(specs)
    return projection.phase_graph, projection.phase_bindings


def _build_provenance(
    resolved: ResolvedProfile,
    *,
    active_specs: tuple[PluginSpec, ...],
    task_contract: str,
    environment: str,
    actor_grant: tuple[str, ...],
) -> PlanProvenance:
    """Build immutable provenance without coupling it to validation passes."""
    return PlanProvenance(
        profile_path=resolved.profile_path,
        bundles=resolved.bundles,
        plugin_revisions=tuple(sorted((spec.id, spec.revision) for spec in active_specs)),
        task_contract=task_contract,
        environment=environment,
        actor_grant=tuple(sorted(actor_grant)),
    )


def _resolve_replacements(
    specs: tuple[PluginSpec, ...],
) -> tuple[tuple[PluginSpec, ...], tuple[ReplacementDecision, ...]]:
    by_id = {spec.id: spec for spec in specs}
    disabled: set[str] = set()
    decisions: list[ReplacementDecision] = []
    for source in specs:
        for relation in source.relations:
            if relation.type is not RelationType.REPLACES:
                continue
            target = by_id.get(relation.target)
            if target is None:
                continue
            decisions.append(
                ReplacementDecision(
                    target=target.id,
                    winner=source.id,
                    mode=relation.mode,
                    reason="declared relation",
                    candidates=(target.id, source.id),
                )
            )
            if relation.mode == "exclusive":
                disabled.add(target.id)
    return tuple(spec for spec in specs if spec.id not in disabled), tuple(decisions)


def _compile_capability_bindings(
    specs: tuple[PluginSpec, ...], resolved: ResolvedProfile
) -> tuple[CapabilityBinding, ...]:
    providers: dict[str, list[tuple[PluginSpec, CapabilityDeclaration]]] = defaultdict(list)
    for spec in specs:
        for capability in spec.provides:
            providers[capability.key].append((spec, capability))
    bindings: list[CapabilityBinding] = []
    for key in sorted(providers):
        candidates = providers[key]
        # Native `one` providers are checked by PluginSpecValidator. The selected
        # provider remains deterministic regardless of import order.
        chosen_spec, chosen = sorted(candidates, key=lambda pair: (pair[0].id, pair[0].revision))[0]
        bindings.append(
            CapabilityBinding(
                capability=key,
                provider=chosen_spec.id,
                cardinality=chosen.cardinality,
                scope=chosen.scope,
                grant=chosen.grant,
                provenance=(resolved.profile_path, chosen_spec.id, chosen_spec.revision),
            )
        )
    return tuple(bindings)


def _compile_control_entries(bindings: tuple[PhaseBinding, ...]) -> tuple[ControlEntry, ...]:
    """Project every declared control contribution into the executable plan.

    Govern contributions own blocking verdicts.  Cross-cutting observe
    contributions are explicit entries as well, preventing an implicit hook
    path for ``observe.checkpoint`` and ``observe.*``.
    """
    entries: list[ControlEntry] = []
    seen: set[tuple[SemanticPhase, str]] = set()
    for binding in bindings:
        for contribution in binding.contributions:
            is_control = (
                contribution.role is ContributionRole.GOVERN
                or contribution.output.startswith("observe.")
            )
            if not is_control:
                continue
            key = (binding.semantic_phase, contribution.executor)
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                ControlEntry(
                    phase=binding.semantic_phase,
                    executor_capability=contribution.executor,
                    predicate="true",
                    aggregation=(
                        contribution.aggregation
                        or (
                            "deny-on-any-deny"
                            if contribution.role is ContributionRole.GOVERN
                            else "all-allow"
                        )
                    ),
                    evidence_required=True,
                )
            )
    return tuple(entries)


__all__ = ["DeclarativePlanProjection", "compile_declarative_projection"]
