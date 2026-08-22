"""ADR-0075 的 PlanCompiler 编译 pass。

该 pass 只把已解析的 Profile 与显式 PluginSpec 变成不可变计划数据；它不导入
具体执行器、不调用 factory，也不在运行时补齐任何 binding。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from lca.contracts.protocols.declarative_phase_graph import (
    DECLARATIVE_PLAN_VERSION,
    CapabilityBinding,
    CapabilityDeclaration,
    CognitivePhaseGraphPlan,
    ContributionRole,
    ControlEntry,
    EffectPolicyPlan,
    EvidenceDeclaration,
    LifecycleDeclaration,
    LoopGuard,
    PhaseBinding,
    PhaseContribution,
    PhaseEdge,
    PhaseGraphValidator,
    PhaseNode,
    PlanProvenance,
    PluginConfiguration,
    PluginImplementation,
    PluginSpec,
    PluginSpecKind,
    PluginSpecValidator,
    RelationType,
    ReplacementDecision,
    SemanticPhase,
    ValidationReport,
    VerificationDeclaration,
)
from lca.harness.plugin_api import PluginDefinition, PluginKind
from lca.harness.profile.resolve import ResolvedPlugin, ResolvedProfile


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
    provenance: PlanProvenance
    validation_report: ValidationReport


def compile_declarative_projection(
    resolved: ResolvedProfile,
    *,
    task_contract: str = "",
    environment: str = "",
    actor_grant: tuple[str, ...] = (),
    include_disabled: bool = False,
) -> DeclarativePlanProjection:
    """编译完整的声明式计划区域。

    已有插件若尚未提供 ``PluginDefinition.spec``，会被一次性投影为强类型
    migration carrier。投影不读取 ``meta``，也不会创建第二套 Profile 或运行计划；
    后续计划哈希始终包含其 revision、配置和关系。
    """

    candidates = tuple(
        item for item in resolved.plugins if include_disabled or not item.disabled
    )
    specs = tuple(_spec_from_resolved(item) for item in candidates if not item.disabled)
    spec_report = PluginSpecValidator().validate(specs)
    active_specs, replacements = _resolve_replacements(specs)
    bindings = _compile_capability_bindings(active_specs, resolved)
    phase_bindings = _compile_phase_bindings(active_specs)
    graph = _compile_phase_graph(phase_bindings, specs)
    controls = _compile_control_entries(phase_bindings)
    effect_policy = _compile_effect_policy(active_specs)
    provenance = PlanProvenance(
        profile_path=resolved.profile_path,
        bundles=resolved.bundles,
        plugin_revisions=tuple(sorted((spec.id, spec.revision) for spec in active_specs)),
        task_contract=task_contract,
        environment=environment,
        actor_grant=tuple(sorted(actor_grant)),
    )
    graph_report = PhaseGraphValidator().validate(
        graph, phase_bindings, active_specs, effect_policy
    )
    report = ValidationReport(spec_report.issues + graph_report.issues)
    return DeclarativePlanProjection(
        schema_version=DECLARATIVE_PLAN_VERSION,
        plugin_specs=active_specs,
        capability_bindings=bindings,
        phase_graph=graph,
        phase_bindings=phase_bindings,
        control_entries=controls,
        replacement_map=replacements,
        effect_policy=effect_policy,
        provenance=provenance,
        validation_report=report,
    )


def _spec_from_resolved(item: ResolvedPlugin) -> PluginSpec:
    definition = item.definition
    declared = definition.spec
    if isinstance(declared, PluginSpec):
        if declared.id != item.id:
            raise ValueError(f"PS-001: PluginSpec id {declared.id!r} != profile id {item.id!r}")
        return declared
    return _project_definition_to_spec(item, definition)


def _project_definition_to_spec(item: ResolvedPlugin, definition: PluginDefinition) -> PluginSpec:
    """将旧 decorator 的 typed 字段投影为 v1 PluginSpec。

    这是 M1 的单向迁移载体：旧 ``meta`` 不在此读取，也不能表达新的 phase、
    relation 或 effect 语义。新插件必须在 decorator 的 ``spec=`` 中提交原生
    PluginSpec；现有 provider 只保留其明确声明的 capability 契约。
    """

    kind_mapping = {
        PluginKind.SEAM: PluginSpecKind.SEAM,
        PluginKind.PROVIDER: PluginSpecKind.PROVIDER,
        PluginKind.PRIMITIVE: PluginSpecKind.PROVIDER,
        PluginKind.COMPOSITE: PluginSpecKind.COMPOSITE,
        PluginKind.DRIVER: PluginSpecKind.DRIVER,
        PluginKind.BRIDGE: PluginSpecKind.PROVIDER,
    }
    group = (
        definition.functional_group.value
        if definition.functional_group is not None
        else "legacy-migration"
    )
    config_name = (
        f"{definition.Config.__module__}.{definition.Config.__name__}"
        if definition.Config is not None
        else "builtins.dict"
    )
    effects = tuple(sorted(effect.value for effect in definition.effects)) or ("none",)
    projected_kind = kind_mapping[definition.kind]
    # A historical seam that declared an external effect is infrastructure in
    # practice. Treat it as a provider during the one-way v1 migration so it
    # remains subject to the effect policy instead of being rejected as a pure seam.
    if projected_kind is PluginSpecKind.SEAM and any(effect != "none" for effect in effects):
        projected_kind = PluginSpecKind.PROVIDER
    return PluginSpec(
        api_version="lca/plugin-spec/v1",
        id=item.id,
        revision="1.0.0",
        kind=projected_kind,
        layer=definition.layer,
        functional_group=group,
        implementation=PluginImplementation(module=item.module, setup="setup"),
        configuration=PluginConfiguration(schema=config_name, values=_config_values(item.config)),
        # Legacy providers are intentionally many: their pre-ADR cardinality is not
        # upgraded implicitly. Native specs define exact cardinality.
        provides=tuple(
            CapabilityDeclaration(key=key, cardinality="many", protocol="object")
            for key in definition.provides
        ),
        requires=tuple(
            CapabilityDeclaration(key=key, cardinality="optional", protocol="object")
            for key in definition.requires
        ),
        effects=effects,
        ownership=__import_ownership(),
        lifecycle=LifecycleDeclaration(scopes=("profile", "run"), activation="true", disposal="required"),
        relations=(),
        evidence=EvidenceDeclaration(emits=("RuntimeObserved",), replay="required"),
        verification=VerificationDeclaration(
            test_suite=definition.test_suite or "tests",
            properties=("typed_plugin_spec",),
        ),
        contributes=(),
    )


def __import_ownership() -> Any:
    # Avoid a large compatibility signature in PluginDefinition while keeping this
    # module's public constructor explicit and typed.
    from lca.contracts.protocols.declarative_phase_graph import OwnershipDeclaration

    return OwnershipDeclaration(state_mutation="forbidden")


def _config_values(config: Any) -> dict[str, Any]:
    if hasattr(config, "model_dump"):
        return dict(config.model_dump(mode="json"))
    if isinstance(config, dict):
        return dict(config)
    return {}


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


def _compile_phase_bindings(specs: tuple[PluginSpec, ...]) -> tuple[PhaseBinding, ...]:
    executors: dict[SemanticPhase, list[tuple[PluginSpec, PhaseContribution]]] = defaultdict(list)
    contributions: dict[SemanticPhase, list[PhaseContribution]] = defaultdict(list)
    for spec in specs:
        for contribution in spec.contributes:
            if spec.kind is PluginSpecKind.PHASE_EXECUTOR:
                executors[contribution.phase].append((spec, contribution))
            else:
                contributions[contribution.phase].append(contribution)
    bindings: list[PhaseBinding] = []
    for phase in SemanticPhase:
        candidates = executors.get(phase, [])
        if not candidates:
            continue
        # A cardinality collision is a compile error recorded by graph validation;
        # choosing deterministically keeps explain/diagnostics total.
        spec, contribution = sorted(candidates, key=lambda item: item[0].id)[0]
        local = tuple(
            sorted(
                contributions.get(phase, ()),
                key=lambda item: (
                    _role_rank(item.role),
                    item.order if item.order is not None else -1,
                    item.executor,
                ),
            )
        )
        bindings.append(
            PhaseBinding(
                node_id=f"{phase.value}.main",
                semantic_phase=phase,
                executor_capability=contribution.executor,
                contributions=local,
            )
        )
    return tuple(bindings)


def _compile_phase_graph(
    bindings: tuple[PhaseBinding, ...], specs: tuple[PluginSpec, ...]
) -> CognitivePhaseGraphPlan:
    node_by_phase = {binding.semantic_phase: binding for binding in bindings}
    nodes = tuple(
        PhaseNode(
            id=binding.node_id,
            semantic_phase=binding.semantic_phase,
            binding=binding.executor_capability,
            max_visits=8,
            terminal=binding.semantic_phase is SemanticPhase.STOP,
        )
        for binding in bindings
    )
    linear = (
        (SemanticPhase.PERCEIVE, SemanticPhase.THINK),
        (SemanticPhase.THINK, SemanticPhase.ACT),
        (SemanticPhase.ACT, SemanticPhase.REFLECT),
        (SemanticPhase.REFLECT, SemanticPhase.REMEMBER),
        (SemanticPhase.REMEMBER, SemanticPhase.STOP),
    )
    edges = [
        PhaseEdge(source=node_by_phase[source].node_id, target=node_by_phase[target].node_id, when="true")
        for source, target in linear
        if source in node_by_phase and target in node_by_phase
    ]
    if SemanticPhase.STOP in node_by_phase and SemanticPhase.PERCEIVE in node_by_phase:
        edges.append(
            PhaseEdge(
                source=node_by_phase[SemanticPhase.STOP].node_id,
                target=node_by_phase[SemanticPhase.PERCEIVE].node_id,
                when="not result.payload.should_stop",
                loop=LoopGuard(
                    max_iterations=8,
                    budget="run.steps",
                    terminal_predicate="result.payload.should_stop",
                ),
            )
        )
    # Add recovery and other declarative edges from plugins
    edges.extend(_compile_phase_edges_from_specs(specs, node_by_phase))
    entry = node_by_phase.get(SemanticPhase.PERCEIVE)
    return CognitivePhaseGraphPlan(
        entry=entry.node_id if entry else "perceive.main",
        nodes=nodes,
        edges=tuple(edges),
    )


def _compile_phase_edges_from_specs(
    specs: tuple[PluginSpec, ...], node_by_phase: dict[SemanticPhase, PhaseBinding]
) -> list[PhaseEdge]:
    """Extract phase edge declarations from plugin specs.

    Plugins that provide "phase.edge.*" capabilities can declare custom edges
    in their configuration. This allows recovery profiles and other control
    flows to add edges to the phase graph declaratively.
    """
    edges: list[PhaseEdge] = []
    for spec in specs:
        # Check if this spec provides a phase edge capability
        if not any(cap.key.startswith("phase.edge.") for cap in spec.provides):
            continue
        # Extract edge configuration from plugin values
        edge_config = spec.configuration.values
        if not edge_config:
            continue
        source = str(edge_config.get("source", ""))
        target = str(edge_config.get("target", ""))
        when = str(edge_config.get("when", "true"))
        if not source or not target:
            continue
        # Parse loop guard if present
        loop_config = edge_config.get("loop")
        loop_guard = None
        if isinstance(loop_config, dict):
            loop_guard = LoopGuard(
                max_iterations=int(loop_config.get("max_iterations", 1)),
                budget=str(loop_config.get("budget", "run.steps")),
                terminal_predicate=str(loop_config.get("terminal_predicate", "false")),
            )
        edges.append(PhaseEdge(source=source, target=target, when=when, loop=loop_guard))
    return edges


def _compile_control_entries(bindings: tuple[PhaseBinding, ...]) -> tuple[ControlEntry, ...]:
    entries: list[ControlEntry] = []
    for binding in bindings:
        for contribution in binding.contributions:
            if contribution.role is ContributionRole.GOVERN:
                entries.append(
                    ControlEntry(
                        phase=binding.semantic_phase,
                        executor_capability=contribution.executor,
                        predicate="true",
                        aggregation=contribution.aggregation or "deny-on-any-deny",
                        evidence_required=True,
                    )
                )
    return tuple(entries)


def _compile_effect_policy(specs: tuple[PluginSpec, ...]) -> EffectPolicyPlan:
    effects = tuple(sorted({effect for spec in specs for effect in spec.effects})) or ("none",)
    return EffectPolicyPlan(
        gateway_capability="effect.gateway",
        allowed_effects=effects,
        approval_required=tuple(effect for effect in effects if effect in {"network", "filesystem", "world"}),
        idempotency_required=tuple(effect for effect in effects if effect != "none"),
    )


def _role_rank(role: ContributionRole) -> int:
    return {
        ContributionRole.PREPARE: 0,
        ContributionRole.TRANSFORM: 1,
        ContributionRole.GOVERN: 2,
        ContributionRole.FINALIZE: 3,
        ContributionRole.OBSERVE: 4,
    }[role]


__all__ = ["DeclarativePlanProjection", "compile_declarative_projection"]
