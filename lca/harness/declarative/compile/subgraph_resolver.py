"""Bundle-relative ``SubgraphResolver`` for compile-time and runtime plan lookup.

ADR-0217:扩展以同时支持两种 bundle 形态:
1. ``bundles/<old>-subgraph.yaml``(entries: 形态,fixture profile 路径走
   ``_PLAN_REF_PROFILES`` → ``_compile_subgraph_profile``)— 保留,reflect-subgraph 用。
2. ``bundles/<new>.yaml``(v2 纯图描述,ADR-0217 BundleGraphSpec)— 新路径,直接读
   yaml → ``BundleGraphSpec`` → ``CognitivePhaseGraphPlan`` → ``CompiledRunPlan``。

职责分工:
- yaml 解析:本模块私有 ``_load_bundle_graph_spec``
- factory → NodeExecutor 解析:委托 ``runtime.resolve_factory``(cordis composite key)
- CognitivePhaseGraphPlan 投影:本模块私有 ``_project_to_phase_graph``
- CompiledRunPlan 包装:本模块私有 ``_wrap_compiled_run_plan``

`interpret()` / registry / Reducer / 任何其它运行时入口一律不感知 bundle 形态差异。
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml

from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphEdge,
    BundleGraphNode,
    BundleGraphSpec,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    CognitivePhaseGraphPlan,
    PhaseEdge,
    PhaseNode,
    SubgraphReference,
    SubgraphResolver,
    ValidationReport,
)
from lca.contracts.protocols.state.plan import COMPILED_RUN_PLAN_VERSION, CompiledRunPlan
from lca.contracts.protocols.state.scope_plan import BudgetCeiling, ScopePlan
from lca.harness.plan import build_input_provenance
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

    The v1 ``compile_declarative_projection`` projection this helper used
    was retired in ADR-0221 P3; v2 ``plan_compile`` does not emit
    ``phase_graph`` on the compiled plan. A v2-native subgraph fixture
    compiler is tracked separately; until it lands this entry point fails
    loud instead of silently importing a deleted module.
    """
    raise NotImplementedError(
        "_compile_subgraph_fixture requires a v2-native subgraph fixture "
        "compiler; the v1 declarative projection was retired in "
        "ADR-0221 P3. The hot path (``compile_plan`` via kernel boot) is "
        "unaffected; only fixtures routed through ``_compile_subgraph_profile`` "
        "hit this gap."
    )


@lru_cache(maxsize=16)
def _compile_subgraph_profile(relative_profile: str) -> CompiledRunPlan:
    profile_path = _repo_root() / relative_profile
    resolved = resolve_profile(profile_path)
    return _compile_subgraph_fixture(resolved)


# ---------------------------------------------------------------------------
# Bundle Graph v2 path (ADR-0217)
# ---------------------------------------------------------------------------


def _parse_sub_spec_ref(raw: Any) -> SubgraphReference | None:
    """Parse yaml ``config.sub_spec_ref`` into a :class:`SubgraphReference`.

    Returns ``None`` if the value is absent. Raises
    :class:`DeclarativeValidationError` if the shape is invalid — fail-loud
    so a typo in the bundle yaml surfaces at compile time, not at driver
    runtime. ADR-0219 §10.11: this is the typed-funnel between yaml DTO
    and ``BundleGraphNode.sub_spec_ref``.
    """
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise DeclarativeValidationError(
            "PG-004",
            f"sub_spec_ref must be a mapping, got {type(raw).__name__}",
        )
    try:
        return SubgraphReference(
            plan_ref=str(raw["plan_ref"]),
            entry_node=str(raw["entry_node"]),
            binding_edge=str(raw["binding_edge"]),
        )
    except KeyError as exc:
        raise DeclarativeValidationError(
            "PG-004",
            f"sub_spec_ref missing required field {exc.args[0]!r}",
        ) from None


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
        # ADR-0219 §10.11: ``sub_spec_ref`` is a typed field on BundleGraphNode,
        # not a config key. Pop it from config so downstream consumers (which
        # see ``config`` as opaque node-level graph params) do not double-handle
        # it. Inner drivers read ``node.sub_spec_ref`` directly.
        raw_config = dict(n.get("config") or {})
        raw_sub_spec_ref = raw_config.pop("sub_spec_ref", None)
        sub_spec_ref = _parse_sub_spec_ref(raw_sub_spec_ref)
        nodes.append(
            BundleGraphNode(
                id=str(n["id"]),
                region=n.get("region"),
                factory=str(n["factory"]),
                purpose=str(n.get("purpose") or ""),
                # ADR-0219 §5.5: bundle yaml 仍容忍 inputs/outputs 字段(向后兼容),
                # 但 runtime 不再读——port contract 由 plugin 的 declared_inputs/declared_outputs
                # typed 属性持有。Loader 静默忽略 yaml 的这两个字段。
                config=raw_config,
                sub_spec_ref=sub_spec_ref,
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
        entry=raw.get("entry"),
    )


def _project_to_phase_graph(
    spec: BundleGraphSpec,
    *,
    runtime: Any | None = None,
) -> tuple[CognitivePhaseGraphPlan, tuple[str, ...]]:
    """BundleGraphSpec → CognitivePhaseGraphPlan。

    每个 BundleGraphNode 投影为 PhaseNode:
      - ``semantic_phase`` 走 ``region`` 反查(默认 THINK,因为本路径只服务 think)
      - ``binding`` 取自 ``BundleGraphNode.factory``(interpreter 进入节点时按
        ``sub_spec_ref`` 短路走子图,不调用该 binding)
      - ``max_visits`` 取自 ``config.max_visits``(默认 1)
      - ``purpose`` / ``inputs`` / ``outputs`` 通过 ``sub_spec_ref.metadata``
        透传(interpreter 启动时读)

    返回 ``(plan, factories_resolved)``。``factories_resolved`` 是已成功解析的
    factory 列表,供 caller 校验用。**Resolve 在此发生**(fail-loud)。

    ``runtime`` 只需暴露 ``resolve_factory(factory, region)`` —— 任何符合
    ``SubgraphRuntime`` 协议(framework 侧)或仅 duck-type 该方法的 stub 均可,
    本模块保留 layer 边界不在此处 import framework。
    """
    region_for_resolve = spec.region
    node_factories: list[tuple[str, str, str | None]] = []  # (node_id, factory, region)
    phase_nodes: list[PhaseNode] = []
    entry_node_id = spec.nodes[0].id

    for n in spec.nodes:
        # ADR-0220 P10: skip factory resolution for nodes carrying a
        # ``sub_spec_ref`` — the framework delegates those nodes to
        # SubgraphRunner (NodeGraphDriver.run:209) and never invokes the
        # factory. The factory field on such nodes is metadata only.
        node_region = n.region if n.region is not None else region_for_resolve
        if runtime is not None and n.sub_spec_ref is None:
            runtime.resolve_factory(n.factory, node_region)  # 命中即返回,失败 fail-loud
        elif runtime is not None:
            # Sub_spec_ref path: validate the factory is at least
            # syntactically present so the YAML surface stays honest.
            if not n.factory:
                raise DeclarativeValidationError(
                    "PG-001",
                    f"node {n.id!r} has sub_spec_ref but no factory field; "
                    "sub_spec_ref delegation requires the node to carry a "
                    "factory (see ADR-0220 §3.5)",
                )
        node_factories.append((n.id, n.factory, node_region))

        max_visits = int(n.config.get("max_visits", 1)) if n.config else 1
        phase_nodes.append(
            PhaseNode(
                id=n.id,
                semantic_phase=SemanticPhase.THINK,
                binding=n.factory,
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
    """v2 CompiledRunPlan 包装(实现 V2BundleGraphPlanMarker)。

    走纯 v2 路径,**不再伪装成老 declarative plan**:
    - phase_graph 含 BundleGraphNode 投影的 PhaseNode(framework 用,但 interpreter
      v2 分支走 NodeGraphDriver,不调 phase executor)
    - phase_bindings:最小合法(GraphAssembler 兜底层,本 ADR 落地后由 NodeGraphDriver
      完全替代)
    - capability / validation_report / provenance:最小合法
    - 实现 V2BundleGraphPlanMarker:isinstance 命中,interpreter 走 v2 分支

    delete-when:interpreter v2 分支稳定后,可进一步精简 phase_bindings / capability /
    validation_report(本 ADR §8 实施步骤 #11)。
    """
    from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
        PhaseBinding,
        PlanProvenance,
    )
    from lca.contracts.protocols.declarative.declarative_1.v2_plan_marker import (
        V2BundleGraphPlanMarker,
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

    class _V2Plan(CompiledRunPlan, V2BundleGraphPlanMarker):
        """v2 plan subclass:实现 V2BundleGraphPlanMarker,挂载 spec。"""

        _spec: BundleGraphSpec

        def get_bundle_graph_spec(self) -> BundleGraphSpec:
            return self._spec

        def __init__(self, **kwargs: Any) -> None:  # type: ignore[no-untyped-def]
            super().__init__(**kwargs)

    plan = _V2Plan(
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
    # frozen dataclass 不让 setattr;用 object.__setattr__ 挂 spec
    object.__setattr__(plan, "_spec", spec)
    return plan


@lru_cache(maxsize=16)
def _compile_bundle_graph(plan_ref: str, *, runtime: Any | None = None) -> CompiledRunPlan:
    """compile one BundleGraph v2 yaml into a CompiledRunPlan. cached per process.

    ``runtime`` 只用于 factory fail-loud 校验,不参与返回 plan 的内容;但
    ``lru_cache`` 会按 (plan_ref, runtime) 同时缓存。生产调用方传同一个
    CordisBackedRuntime 实例,缓存命中率不变。
    """
    spec = _load_bundle_graph_spec(plan_ref)
    phase_graph, _factories = _project_to_phase_graph(spec, runtime=runtime)
    return _wrap_compiled_run_plan(spec, phase_graph)


class BundleSubgraphResolver:
    """Resolve ``SubgraphReference.plan_ref`` bundle paths to ``CompiledRunPlan``,
    AND duck-type the SubgraphRuntime ``resolve_factory`` seam so the same
    instance can be passed both as ``resolver=`` and ``runtime=``.

    两条解析路径:
    1. ``_PLAN_REF_PROFILES`` 命中 → fixture profile → CompiledRunPlan(legacy,
       reflect-subgraph 用,保留)
    2. ``bundles/<file>.yaml`` 文件存在 + 能解析为 BundleGraphSpec → v2 新路径
       (think.yaml 等用)

    v2 路径在 ``runtime=None`` 时仍编译(yaml 合法性校验),但跳过
    ``resolve_factory`` 校验;v2 driver runtime 时由 scope.resolve_factory 真实取实例。

    双职责集成(SubgraphResolver + SubgraphRuntime)消除两套注册表的边界冗余。
    """

    def resolve(self, plan_ref: str, *, runtime: Any | None = None) -> CompiledRunPlan | None:
        relative_profile = _PLAN_REF_PROFILES.get(plan_ref)
        if relative_profile is not None:
            return _compile_subgraph_profile(relative_profile)
        # v2 新路径:plan_ref 以 ``bundles/`` 开头 + 文件存在 + 顶层含 ``nodes:``
        if _is_bundle_graph_v2(plan_ref):
            return _compile_bundle_graph(plan_ref, runtime=runtime)
        return None

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        """Duck-type SubgraphRuntime.resolve_factory seam。

        本 resolver 不持有 NodeExecutor 实例(那是 SubgraphRunner / v2 driver 的职责)。
        本方法返回 None 表示 "此 resolver 不解析实例,请改用 v2 driver runtime
        scope" —— 这是 fail-soft,不是 fail-loud;真正的 fail-loud 由 v2 driver
        在 instance lookup miss 时触发(``scope.resolve_factory``)。

        这个集成让 interpreter 可以把同一个 ``BundleSubgraphResolver`` 实例
        通过 ``subgraph_resolver=`` 传给 ``SubgraphRunner``,无需额外
        runtime-side wrapping;``SubgraphRunner`` 内部通过
        ``PluginContextBackedRuntime`` 拿到 capability。
        """
        del factory, region
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
    "resolve_factory",
]
