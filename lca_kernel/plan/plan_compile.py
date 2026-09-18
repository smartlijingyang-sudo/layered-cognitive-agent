"""V2 kernel-native plan compilation (replaces
``lca.harness.composition.plan_compiler.compile_plan``).

The v1 plan compiler emitted ``phase_graph`` + ``phase_bindings`` regions
that the v0 ``GraphAssembler`` consumed. ADR-0221 P3 retires those
regions: the v2 runtime builds its executable plan directly from
``PlanInterpreter`` + NodeExecutor subgraphs, so the compiled plan no
longer carries a declarative phase graph. This module emits a v2 plan
with ``phase_graph=None`` and an empty ``phase_bindings`` tuple.

Replaces ``lca.harness.composition.plan_compiler``. The ``CompileOptions``
shape is preserved so existing callers (kernel boot, tests) continue to
work; only the v1-only fields are no-ops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.models.assistant.plan_overlay import PlanOverlay
from lca.contracts.models.cognition.prompt_assembly import (
    BUILTIN_PROMPT_TEMPLATE_IDS,
    REGISTERED_PROMPT_SECTION_NAMES,
)
from lca.contracts.protocols.state.plan import (
    COMPILED_RUN_PLAN_VERSION,
    CompiledRunPlan,
)
from lca.contracts.protocols.state.scope_plan import BudgetCeiling, ScopePlan
from lca.harness.declarative.compile.action.authority import compile_action_authority
from lca.harness.profile.resolve.capability_plan_resolver import (
    CapabilityPlanOptions,
    project_capability_plan,
)
from lca.harness.profile.resolve.resolve import ResolvedProfile


class PlanCompilerError(ValueError):
    """PlanCompiler 编译失败（profile 不合法 / 子 plan 投影失败）。"""


@dataclass(frozen=True, slots=True)
class V2ExecutablePlan:
    """CompiledRunPlan + the v2 graph spec lifted from the resolved bundle.

    ADR-0221 P3: the runtime kernel no longer rebuilds an executable
    plan via v0 ``GraphAssembler``. Instead, the kernel reads the v2
    graph (``nodes``/``edges``) straight from the bundle yaml. This
    wrapper carries that spec alongside the immutable compiled plan so
    ``DeclarativeRuntimeDriver`` can hand the graph to
    ``PlanInterpreter`` directly.
    """

    inner: object  # CompiledRunPlan — typed loosely to avoid cycle import.

    def __getattr__(self, name: str):
        # Delegate CompiledRunPlan surface to ``inner`` so legacy callers
        # that touch ``plan.plan_version`` / ``plan.phase_graph`` / etc.
        # still work without knowing about the wrapper. The wrapper itself
        # exposes only ``inner`` / ``graph_spec`` / ``profile_path`` /
        # ``plugin_specs`` explicitly; everything else falls through.
        return getattr(self.inner, name)

    graph_spec: dict = field(default_factory=dict)
    profile_path: str = ""
    plugin_specs: tuple = ()  # delegated to ``inner.plugin_specs`` at construction; surfaced here so CLI / introspection see the catalog without reaching into ``inner``.


def _resolve_bundle_path(entry: str, resolved: ResolvedProfile) -> Path:
    """把 bundle 引用解析为文件路径（相对 profile 目录的条目先归一化）。"""
    path = Path(entry)
    if not path.exists():
        profile = Path(resolved.profile_path or ".")
        candidate = profile.parent / entry
        if candidate.exists():
            path = candidate
    return path


def _apply_subgraph_overrides(graph_spec: dict, subgraph_overrides: dict[str, str]) -> None:
    """把 outer plan 中 ``region: phase:<name>`` 节点的 ``sub_spec_ref.plan_ref``
    改写为 plan.yaml 声明的实验 bundle 路径（ADR-0242 D10）。

    ``graph_spec`` 是每次编译从 yaml 新读出的 dict，原地改写安全；运行期
    ``BundleSubgraphResolver`` 按 ``sub_spec_ref.plan_ref`` 解析子图，因此
    改这里即改运行期 phase 子图组合。
    """
    for node in graph_spec.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        region = str(node.get("region", ""))
        if not region.startswith("phase:"):
            continue
        phase = region[len("phase:") :]
        new_path = subgraph_overrides.get(phase)
        if new_path is None:
            continue
        sub_spec_ref = node.get("sub_spec_ref")
        if isinstance(sub_spec_ref, dict):
            sub_spec_ref["plan_ref"] = new_path


def _wrap_v2_plan(plan, *, resolved, overlay: PlanOverlay | None = None):
    """Read the v2 graph spec from the resolved bundle yaml.

    Falls back to an empty graph when no bundle carries ``nodes``/
    ``edges`` — the interpreter will terminate immediately, which is
    the desired fail-loud signal for a missing bundle.

    ``overlay`` 非空时（ADR-0242 D10）：把 phase 子图 bundle 路径替换为
    plan.yaml 声明的实验路径，并改写 outer plan 的 ``sub_spec_ref``。
    """

    graph_spec = {"id": resolved.profile_path, "nodes": [], "edges": []}
    bundles = getattr(resolved, "bundles", ()) or ()
    subgraph_overrides = dict(overlay.graph.subgraphs) if overlay is not None else {}
    for entry in bundles:
        if not isinstance(entry, str):
            continue
        path = _resolve_bundle_path(entry, resolved)
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not (isinstance(data, dict) and ("nodes" in data or "edges" in data)):
            continue
        # ADR-0221 P3 + outer-plan cutover: a phase subgraph bundle has
        # ``id: <phase>.subgraph`` and is meant to be entered through a
        # ``sub_spec_ref`` on the outer plan node, not executed as the
        # outer plan itself. Skip any bundle whose id ends in
        # ``.subgraph`` so the outer plan (``id`` not ending in
        # ``.subgraph``) is selected as the v2 graph spec.
        bundle_id = str(data.get("id", ""))
        if bundle_id.endswith(".subgraph"):
            region = str(data.get("region", "")) or bundle_id[: -len(".subgraph")]
            if region in subgraph_overrides:
                # 覆盖路径必须可解析为 v2 bundle graph（fail-closed）。
                entry = subgraph_overrides[region]
                path = _resolve_bundle_path(entry, resolved)
                if not path.is_file():
                    raise PlanCompilerError(
                        f"plan.yaml 子图覆盖 bundle 不存在: {entry!r} (phase={region!r})"
                    )
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                if not (isinstance(data, dict) and "nodes" in data):
                    raise PlanCompilerError(
                        f"plan.yaml 子图覆盖不是 v2 bundle graph: {entry!r} (phase={region!r})"
                    )
            continue
        graph_spec = data
        break
    if subgraph_overrides:
        _apply_subgraph_overrides(graph_spec, subgraph_overrides)
    # ADR-0221 P3: when no node carries ``entry: true``, mark the first
    # node as the entry so the v2 traversal has a starting point.
    nodes = graph_spec.get("nodes") or []
    if nodes and not any(node.get("entry") for node in nodes if isinstance(node, dict)):
        nodes[0]["entry"] = True
        graph_spec["nodes"] = nodes
    return V2ExecutablePlan(
        inner=plan,
        graph_spec=graph_spec,
        profile_path=resolved.profile_path,
        plugin_specs=getattr(plan, "plugin_specs", ()) or (),
    )


@dataclass(frozen=True, slots=True)
class CompileOptions:
    """PlanCompiler 的已验证编译输入（v2 — phase 字段已 no-op）。"""

    lifecycle: Scope = Scope.RUN
    visibility: tuple[Scope, ...] = ()
    acl_grants: tuple[str, ...] = ()
    budget_ceiling: BudgetCeiling | None = None
    task_id: str | None = None
    env_fingerprint: str | None = None
    include_disabled: bool = False
    # ADR-0221 P3: ``require_executable_phase_graph`` is ignored. The v2
    # plan does not carry a declarative phase graph; runtime builds the
    # executable plan from NodeExecutor subgraphs at boot.
    require_executable_phase_graph: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.lifecycle, Scope):
            raise TypeError("lifecycle must be a Scope")
        if not isinstance(self.visibility, tuple) or any(
            not isinstance(scope, Scope) for scope in self.visibility
        ):
            raise TypeError("visibility must be a tuple of Scope values")
        if not isinstance(self.acl_grants, tuple) or any(
            not isinstance(grant, str) or not grant.strip() for grant in self.acl_grants
        ):
            raise TypeError("acl_grants must be a tuple of non-empty strings")
        if self.budget_ceiling is not None and not isinstance(self.budget_ceiling, BudgetCeiling):
            raise TypeError("budget_ceiling must be a BudgetCeiling or None")
        for _field, value in (
            ("task_id", self.task_id),
            ("env_fingerprint", self.env_fingerprint),
        ):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field} must be a string or None")
        if not isinstance(self.include_disabled, bool):
            raise TypeError("include_disabled must be a boolean")
        if not isinstance(self.require_executable_phase_graph, bool):
            raise TypeError("require_executable_phase_graph must be a boolean")


def _known_template_ids(resolved: ResolvedProfile) -> frozenset[str]:
    """返回可登记的模板 id 闭集：内建模板 + profile 声明的扩展模板。"""
    ids = set(BUILTIN_PROMPT_TEMPLATE_IDS)
    for plugin in getattr(resolved, "plugins", ()):
        cfg = getattr(plugin, "config", None)
        profile_templates = getattr(cfg, "profile_templates", None)
        if not profile_templates:
            continue
        for tpl in profile_templates:
            tid = getattr(tpl, "id", None)
            if tid:
                ids.add(tid)
    return frozenset(ids)


def _validate_overlay_registrations(resolved: ResolvedProfile, overlay: PlanOverlay) -> None:
    """plan.yaml 只能组合**已登记**模板 / section / bundle（ADR-0242 I-B11）。

    - 模板 id ∈ 内建 + profile 声明模板注册表；
    - section 名 ∈ 既有 section 注册表闭集；
    - 子图 bundle 路径可解析为 v2 bundle graph（``nodes`` 存在）。

    任一项不满足 ⇒ ``PlanCompilerError``（fail-closed），不静默忽略。
    """
    if overlay.prompt.template is not None:
        known = _known_template_ids(resolved)
        if overlay.prompt.template not in known:
            raise PlanCompilerError(
                f"plan.yaml 模板未登记: {overlay.prompt.template!r};"
                f"已知模板: {', '.join(sorted(known))}"
            )
    for section in overlay.prompt.sections:
        if section.name not in REGISTERED_PROMPT_SECTION_NAMES:
            raise PlanCompilerError(
                f"plan.yaml section 未登记: {section.name!r};"
                f"已知 section: {', '.join(sorted(REGISTERED_PROMPT_SECTION_NAMES))}"
            )
    for phase, bundle_path in overlay.graph.subgraphs.items():
        path = _resolve_bundle_path(bundle_path, resolved)
        if not path.is_file():
            raise PlanCompilerError(
                f"plan.yaml 子图覆盖 bundle 不存在: {bundle_path!r} (phase={phase!r})"
            )
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not (isinstance(data, dict) and "nodes" in data):
            raise PlanCompilerError(
                f"plan.yaml 子图覆盖不是 v2 bundle graph: {bundle_path!r} (phase={phase!r})"
            )


def compile_plan(
    resolved: ResolvedProfile,
    *,
    options: CompileOptions | None = None,
    overlay: PlanOverlay | None = None,
) -> CompiledRunPlan:
    """Compile ``ResolvedProfile`` into an immutable ``CompiledRunPlan``.

    v2 shape: ``phase_graph`` 永远是 None、``phase_bindings`` 永远为空。
    需要可执行图的调用方在 boot 时向 ``PlanInterpreter`` 索取。

    ``plugin_specs`` 是 resolved profile 上每个启用
    :class:`~lca.contracts.protocols.declarative.declarative_2.declarative_plugin.PluginSpec`
    的投影（ADR-0221 P3）。CLI 面（``lca-ops kernel_compose --json``、
    ``V2ExecutablePlan.plugin_specs``）据此枚举已加载插件目录而无需重跑
    ``resolve_profile``。

    ``overlay``（ADR-0242 D10）：per-agent ``plan.yaml`` 覆盖。非空时：
    1. 校验模板 / section / bundle 均已登记（I-B11 fail-closed）；
    2. 子图覆盖改写 v2 bundle walk 与 outer plan 的 ``sub_spec_ref``；
    3. prompt 覆盖附着到 ``CompiledRunPlan`` 的新字段。

    ``overlay=None`` 时行为与启用前完全一致（I-B8：无 assistant 路径
    byte-identical）。
    """
    opts = options or CompileOptions()
    if overlay is not None:
        _validate_overlay_registrations(resolved, overlay)
    cap_options = CapabilityPlanOptions(include_disabled=opts.include_disabled)
    capability = project_capability_plan(resolved, options=cap_options)
    scope = ScopePlan(
        profile_path=resolved.profile_path,
        lifecycle=opts.lifecycle,
        visibility=opts.visibility,
        acl_grants=opts.acl_grants,
        budget_ceiling=opts.budget_ceiling or BudgetCeiling(),
    )
    plugin_specs: tuple = tuple(
        plugin.definition.spec for plugin in resolved.plugins if not plugin.disabled
    )
    return _wrap_v2_plan(
        CompiledRunPlan(
            profile_path=resolved.profile_path,
            capability=capability,
            scope=scope,
            plan_version=COMPILED_RUN_PLAN_VERSION,
            revision="v2",
            plugin_specs=plugin_specs,
            capability_bindings=capability.provider_bindings,
            # v2 ADR-0221 P3: phase_graph + phase_bindings retired from
            # CompiledRunPlan; runtime builds the executable plan via
            # PlanInterpreter + NodeExecutor subgraphs at boot.
            # Empty ActionAuthorityPlan() left Body registry vacant ->
            # UnregisteredActionError on use_tool; the loop is then
            # bounded by AgentState.budget (max_steps, max_wall_clock)
            # plus per-node terminal_predicate (ADR-0225: the prior
            # max_visits per-node ceiling is gone).
            # Empty plugin_specs => SOLO defaults (respond/use_tool/stop/ask_human).
            action_authority=compile_action_authority(()),
            # ADR-0242 D10: per-agent prompt 覆盖附着到编译计划（L3 数据变换）。
            prompt_template_id=overlay.prompt.template if overlay is not None else None,
            prompt_section_overrides=overlay.prompt.sections if overlay is not None else (),
        ),
        resolved=resolved,
        overlay=overlay,
    )


__all__ = [
    "COMPILED_RUN_PLAN_VERSION",
    "CompileOptions",
    "CompiledRunPlan",
    "PlanCompilerError",
    "compile_plan",
]
