"""Bundle-relative ``SubgraphResolver`` for compile-time and runtime plan lookup.

ADR-0217:扩展以同时支持两种 bundle 形态:
1. ``bundles/<old>-subgraph.yaml``(entries: 形态,fixture profile 路径走
   ``_PLAN_REF_PROFILES`` → ``_compile_subgraph_profile``)— 保留,reflect-subgraph 用。
2. ``bundles/<new>.yaml``(v2 纯图描述,ADR-0217 BundleGraphSpec)— 新路径,直接读
   yaml → ``BundleGraphSpec`` → ``CognitivePhaseGraphPlan`` → ``CompiledRunPlan``。

职责分工:
- yaml 解析:本模块私有 ``_load_bundle_graph_spec``
- factory → NodeExecutor 解析:委托 ``FactoryRegistry.resolve``
- CognitivePhaseGraphPlan 投影:本模块私有 ``_project_to_phase_graph``
- CompiledRunPlan 包装:本模块私有 ``_wrap_compiled_run_plan``

`interpret()` / registry / Reducer / 任何其它运行时入口一律不感知 bundle 形态差异。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

import yaml

from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphEdge,
    BundleGraphNode,
    BundleGraphSpec,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    CognitivePhaseGraphPlan,
    PhaseEdge,
    PhaseNode,
    SubgraphResolver,
    ValidationReport,
)
from lca.contracts.protocols.declarative.declarative_1.factory_resolver import (
    get_default_registry,
)
from lca.contracts.protocols.state.plan import COMPILED_RUN_PLAN_VERSION, CompiledRunPlan
from lca.contracts.protocols.state.scope_plan import BudgetCeiling, ScopePlan
from lca.harness.declarative.compile.compiler.compiler import compile_declarative_projection
from lca.harness.declarative.controls.validation import PhaseGraphValidator, require_valid
from lca.harness.plan import build_input_provenance
from lca.harness.profile.plan.projection import ProfileCompilationProjections
from lca.harness.profile.resolve.capability_plan_resolver import (
    CapabilityPlanOptions,
    project_capability_plan,
)
from lca.harness.profile.resolve.resolve import ResolvedProfile, resolve_profile

# Bundle path → fixture profile that compiles the subgraph in isolation.
# Profiles live under ``profiles/fixtures/`` and are not production defaults.
_PLAN_REF_PROFILES: Final[dict[str, str]] = {
    "bundles/reflect-subgraph.yaml": "profiles/fixtures/reflect-subgraph-compile.yaml",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _compile_subgraph_fixture(resolved: ResolvedProfile) -> CompiledRunPlan:
    """Compile one subgraph fixture profile without production runtime closure.

    Subgraph bundles only need the declarative phase graph projection. They
    must not pull in the full production runtime seam closure that a
    runnable profile like ``web-standard`` requires.
    """

    projections = ProfileCompilationProjections.build(resolved)
    declarative = compile_declarative_projection(
        resolved,
        task_contract="subgraph-fixture",
        environment="subgraph-fixture",
        actor_grant=(),
        projection=projections.selected,
    )
    if declarative.phase_graph is None:
        raise ValueError(
            f"subgraph fixture profile {resolved.profile_path!r} produced no phase graph"
        )
    subgraph_report = PhaseGraphValidator().validate(
        declarative.phase_graph,
        declarative.phase_bindings,
        declarative.plugin_specs,
        declarative.effect_policy,
        require_all_semantic_phases=False,
    )
    require_valid(subgraph_report)
    capability = project_capability_plan(
        resolved,
        options=CapabilityPlanOptions(),
        projection=projections.selected,
    )
    scope = ScopePlan(
        profile_path=resolved.profile_path,
        lifecycle=Scope.RUN,
        visibility=tuple(Scope),
        acl_grants=(),
        budget_ceiling=BudgetCeiling(),
        revision="v1",
    )
    input_provenance = build_input_provenance(
        profile_path=resolved.profile_path,
        bundles=resolved.bundles,
        patches=(),
        task_id=None,
        env_fingerprint=None,
    )
    return CompiledRunPlan(
        profile_path=resolved.profile_path,
        capability=capability,
        scope=scope,
        plan_version=COMPILED_RUN_PLAN_VERSION,
        input_provenance=input_provenance,
        revision="v3",
        plugin_specs=declarative.plugin_specs,
        capability_bindings=declarative.capability_bindings,
        phase_graph=declarative.phase_graph,
        phase_bindings=declarative.phase_bindings,
        control_entries=declarative.control_entries,
        replacement_map=declarative.replacement_map,
        effect_policy=declarative.effect_policy,
        action_authority=declarative.action_authority,
        provenance=declarative.provenance,
        validation_report=subgraph_report,
    )


@lru_cache(maxsize=16)
def _compile_subgraph_profile(relative_profile: str) -> CompiledRunPlan:
    profile_path = _repo_root() / relative_profile
    resolved = resolve_profile(profile_path)
    return _compile_subgraph_fixture(resolved)


# ---------------------------------------------------------------------------
# Bundle Graph v2 path (ADR-0217)
# ---------------------------------------------------------------------------


def _load_bundle_graph_spec(plan_ref: str) -> BundleGraphSpec:
    """从 yaml 文件读取并构造 BundleGraphSpec。

    职责:yaml → dict → BundleGraphSpec。失败抛 DeclarativeValidationError。
    """
    path = _repo_root() / plan_ref
    if not path.is_file():
        raise FileNotFoundError(f"bundle graph yaml not found: {plan_ref}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"bundle graph yaml must be a mapping at top level, got {type(raw).__name__}")

    # nodes 解析
    raw_nodes = raw.get("nodes") or ()
    if not isinstance(raw_nodes, (list, tuple)):
        raise TypeError("nodes must be a list")
    nodes: list[BundleGraphNode] = []
    for n in raw_nodes:
        if not isinstance(n, dict):
            raise TypeError(f"each node must be a mapping, got {type(n).__name__}")
        nodes.append(
            BundleGraphNode(
                id=str(n["id"]),
                region=n.get("region"),
                factory=str(n["factory"]),
                purpose=str(n["purpose"]),
                inputs=tuple(n.get("inputs") or ()),
                outputs=tuple(n.get("outputs") or ()),
                config=dict(n.get("config") or {}),
            )
        )

    # edges 解析(支持 yaml `from:` / `to:` 别名)
    raw_edges = raw.get("edges") or ()
    if not isinstance(raw_edges, (list, tuple)):
        raise TypeError("edges must be a list")
    edges: list[BundleGraphEdge] = []
    for e in raw_edges:
        if not isinstance(e, dict):
            raise TypeError(f"each edge must be a mapping, got {type(e).__name__}")
        edges.append(
            BundleGraphEdge.from_kwargs(
                source=str(e.get("source") or e.get("from") or ""),
                target=str(e.get("target") or e.get("to") or ""),
                kind=e.get("kind", "control"),
                when=str(e.get("when", "true")),
            )
        )

    return BundleGraphSpec(
        id=str(raw.get("id") or path.stem),
        region=raw.get("region"),
        purpose=raw.get("purpose"),
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def _project_to_phase_graph(
    spec: BundleGraphSpec,
) -> tuple[CognitivePhaseGraphPlan, tuple[str, ...]]:
    """BundleGraphSpec → CognitivePhaseGraphPlan。

    每个 BundleGraphNode 投影为 PhaseNode:
      - ``semantic_phase`` 走 ``region`` 反查(默认 THINK,因为本路径只服务 think)
      - ``binding`` 用占位 ``phase.think.standard``(interpreter 进入节点时按
        ``sub_spec_ref`` 短路走子图,不调用该 binding)
      - ``max_visits`` 取自 ``config.max_visits``(默认 1)
      - ``purpose`` / ``inputs`` / ``outputs`` 通过 ``sub_spec_ref.metadata``
        透传(interpreter 启动时读)

    返回 ``(plan, factories_resolved)``。``factories_resolved`` 是已成功解析的
    factory 列表,供 caller 校验用。**Resolve 在此发生**(fail-loud)。
    """
    registry = get_default_registry()
    region_for_resolve = spec.region
    node_factories: list[tuple[str, str, str | None]] = []  # (node_id, factory, region)
    phase_nodes: list[PhaseNode] = []
    entry_node_id = spec.nodes[0].id

    for n in spec.nodes:
        # 规则 1:解析 factory(失败抛 FactoryResolutionError,PG-005-factory)
        node_region = n.region if n.region is not None else region_for_resolve
        registry.resolve(n.factory, node_region)  # 命中即返回,失败 fail-loud
        node_factories.append((n.id, n.factory, node_region))

        max_visits = int(n.config.get("max_visits", 1)) if n.config else 1
        phase_nodes.append(
            PhaseNode(
                id=n.id,
                semantic_phase=SemanticPhase.THINK,
                binding="phase.think.standard",  # 占位,interpreter 短路
                max_visits=max_visits,
            )
        )

    phase_edges = tuple(
        PhaseEdge(source=e.source, target=e.target, when=e.when) for e in spec.edges
    )

    return CognitivePhaseGraphPlan(entry=entry_node_id, nodes=tuple(phase_nodes), edges=phase_edges), tuple(
        f for _, f, _ in node_factories
    )


def _wrap_compiled_run_plan(
    spec: BundleGraphSpec,
    phase_graph: CognitivePhaseGraphPlan,
) -> CompiledRunPlan:
    """最小 CompiledRunPlan 包装(只填 interpreter 必需的字段)。

    给每个 BundleGraphNode 投影一个 PhaseBinding,让 GraphAssembler 能装配。
    ``executor_capability`` 固定为 ``phase.think.standard``,interpreter 进入
    节点时按 ``sub_spec_ref`` 短路走子图,不调用该 binding;此处只为满足
    GraphAssembler 的 Pydantic 必填字段。

    CapabilityPlan 必须合法(``capability_plan_hash`` 读 provider_bindings),
    即使 v2 路径下 plugin 注册职责在 cordis 不在 plan;这里给空 plan 即可,
    interpreter 走 sub_spec_ref 短路后不会再用。
    """
    from lca.contracts.protocols.composition.relation import TypedRelation
    from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
        PhaseBinding,
        PlanProvenance,
    )
    from lca.contracts.protocols.perceive.capability_plan import CapabilityPlan

    profile_path = str(_repo_root() / "bundles/__bundle_graph_v2_stub__.yaml")
    scope = ScopePlan(
        profile_path=profile_path,
        lifecycle=Scope.RUN,
        visibility=tuple(Scope),
        acl_grants=(),
        budget_ceiling=BudgetCeiling(),
        revision="v1",
    )
    input_provenance = build_input_provenance(
        profile_path=profile_path,
        bundles=(spec.id,),
        patches=(),
        task_id=None,
        env_fingerprint=None,
    )
    phase_bindings = tuple(
        PhaseBinding(
            node_id=n.id,
            semantic_phase=n.semantic_phase,
            executor_capability=n.binding,
        )
        for n in phase_graph.nodes
    )
    capability = CapabilityPlan(
        profile_path=profile_path,
        provider_bindings=(),
        relations=(),
        revision="v1",
    )
    plan_provenance = PlanProvenance(
        profile_path=profile_path,
        bundles=(spec.id,),
        task_contract="bundle-graph-v2",
        environment="bundle-graph-v2",
    )
    return CompiledRunPlan(
        profile_path=profile_path,
        capability=capability,
        scope=scope,
        plan_version=COMPILED_RUN_PLAN_VERSION,
        input_provenance=input_provenance,
        revision="v3",
        plugin_specs=(),
        capability_bindings=(),
        phase_graph=phase_graph,
        phase_bindings=phase_bindings,
        control_entries=(),
        replacement_map=(),
        effect_policy=(),
        action_authority=(),
        provenance=plan_provenance,
        validation_report=ValidationReport(issues=()),
    )


@lru_cache(maxsize=16)
def _compile_bundle_graph(plan_ref: str) -> CompiledRunPlan:
    """compile one BundleGraph v2 yaml into a CompiledRunPlan. cached per process."""
    spec = _load_bundle_graph_spec(plan_ref)
    phase_graph, _factories = _project_to_phase_graph(spec)
    return _wrap_compiled_run_plan(spec, phase_graph)


class BundleSubgraphResolver:
    """Resolve ``SubgraphReference.plan_ref`` bundle paths to ``CompiledRunPlan``.

    两条路径:
    1. ``_PLAN_REF_PROFILES`` 命中 → fixture profile → CompiledRunPlan(legacy,
       reflect-subgraph 用,保留)
    2. ``bundles/<file>.yaml`` 文件存在 + 能解析为 BundleGraphSpec → v2 新路径
       (think.yaml 等用)
    """

    def resolve(self, plan_ref: str) -> CompiledRunPlan | None:
        relative_profile = _PLAN_REF_PROFILES.get(plan_ref)
        if relative_profile is not None:
            return _compile_subgraph_profile(relative_profile)
        # v2 新路径:plan_ref 以 ``bundles/`` 开头 + 文件存在 + 顶层含 ``nodes:``
        if _is_bundle_graph_v2(plan_ref):
            return _compile_bundle_graph(plan_ref)
        return None


def _is_bundle_graph_v2(plan_ref: str) -> bool:
    """sniff:plan_ref 是否指向 v2 BundleGraphSpec 形态的 yaml。"""
    if not plan_ref.startswith("bundles/") or not plan_ref.endswith(".yaml"):
        return False
    path = _repo_root() / plan_ref
    if not path.is_file():
        return False
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return False
    return isinstance(raw, dict) and isinstance(raw.get("nodes"), (list, tuple))


def default_subgraph_resolver() -> SubgraphResolver:
    """Return the production bundle-relative subgraph resolver."""

    return BundleSubgraphResolver()


__all__ = [
    "BundleSubgraphResolver",
    "_compile_bundle_graph",
    "default_subgraph_resolver",
]
