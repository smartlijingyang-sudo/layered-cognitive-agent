"""Compile resolved profiles into immutable runtime plans.

``compile_plan()`` 把 ``ResolvedProfile`` 编译为不可变
``CompiledRunPlan = CapabilityPlan + ScopePlan + 声明式执行区域``。控制贡献仅由
原生 ``PluginSpec`` 投影为 ``control_entries``；解释和序列化投影位于
``plan_explain``，避免编译器同时承担诊断展示职责。
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.declarative.declarative_phase_graph import SemanticPhase
from lca.contracts.protocols.state.plan import COMPILED_RUN_PLAN_VERSION, CompiledRunPlan
from lca.contracts.protocols.state.scope_plan import BudgetCeiling, ScopePlan
from lca.harness.declarative.compile.compiler import (
    DeclarativePlanProjection,
    compile_declarative_projection,
)
from lca.harness.declarative.controls.validation import require_valid
from lca.harness.plan import build_input_provenance
from lca.harness.profile.capability_plan_resolver import (
    CapabilityPlanOptions,
    project_capability_plan,
)
from lca.harness.profile.plan_explain import explain_compile_plan
from lca.harness.profile.projection import ProfileCompilationProjections
from lca.harness.profile.resolve import ResolvedProfile
from lca.harness.profile.runtime_binding_validator import validate_runtime_closure


class PlanCompilerError(ValueError):
    """PlanCompiler 编译失败（profile 不合法 / 子 plan 投影失败）。"""


@dataclass(frozen=True, slots=True)
class CompileOptions:
    """PlanCompiler 的已验证编译输入。

    ``compile_plan`` 依据这些值选择 Profile 投影、runtime closure 和
    executable phase-graph 验证路径。因此本对象是编译入口的类型闭合 seam：
    不允许将配置文本、宽松序列或真值型替代物带入下游分支。
    """

    lifecycle: Scope = Scope.RUN
    visibility: tuple[Scope, ...] = ()
    acl_grants: tuple[str, ...] = ()
    budget_ceiling: BudgetCeiling | None = None
    task_id: str | None = None
    env_fingerprint: str | None = None
    include_disabled: bool = False
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
        for field, value in (
            ("task_id", self.task_id),
            ("env_fingerprint", self.env_fingerprint),
        ):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field} must be a string or None")
        if not isinstance(self.include_disabled, bool):
            raise TypeError("include_disabled must be a boolean")
        if not isinstance(self.require_executable_phase_graph, bool):
            raise TypeError("require_executable_phase_graph must be a boolean")


def compile_plan(
    resolved: ResolvedProfile,
    *,
    options: CompileOptions | None = None,
) -> CompiledRunPlan:
    """Compile ``ResolvedProfile`` into an immutable ``CompiledRunPlan``.

    The compiler validates production runtime closure, projects the capability,
    control and scope sub-plans, then embeds the declarative phase graph and its
    provenance. It never constructs runtime providers or fills missing bindings.
    """
    opts = options or CompileOptions()
    cap_options = CapabilityPlanOptions(include_disabled=opts.include_disabled)
    projections = ProfileCompilationProjections.build(
        resolved,
        include_disabled=opts.include_disabled,
    )

    # W1 / ADR-0076: production profiles must provide the complete runtime
    # closure before any executable plan can be assembled.  This deliberately
    # reads the active view even when the selected plan is for inspection.
    validate_runtime_closure(resolved, projection=projections.active)

    capability = project_capability_plan(
        resolved,
        options=cap_options,
        projection=projections.selected,
    )
    scope = _build_scope_plan(resolved, opts)

    patches = tuple(
        f"{resolved.profile_path}#patch.{item.id}"
        for item in sorted(resolved.plugins, key=lambda item: item.index)
        if "+patch" in item.source
    )
    input_provenance = build_input_provenance(
        profile_path=resolved.profile_path,
        bundles=resolved.bundles,
        patches=patches,
        task_id=opts.task_id,
        env_fingerprint=opts.env_fingerprint,
    )
    declarative = compile_declarative_projection(
        resolved,
        task_contract=opts.task_id or "",
        environment=opts.env_fingerprint or "",
        actor_grant=tuple(opts.acl_grants),
        include_disabled=opts.include_disabled,
        projection=projections.selected,
    )
    # Runnable plans must be validated before crossing the binding seam.  Pure
    # inspection profiles may intentionally omit phase bindings and retain the
    # projection's diagnostic report for callers that only inspect plans.
    if opts.require_executable_phase_graph:
        _require_executable_phase_graph(declarative)
    if declarative.phase_bindings or _has_declarative_bundle(resolved):
        require_valid(declarative.validation_report)

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
        validation_report=declarative.validation_report,
    )


def _has_declarative_bundle(resolved: ResolvedProfile) -> bool:
    """Return whether the profile explicitly opts into declarative execution."""
    return any("declarative-phase-graph" in bundle for bundle in resolved.bundles)


def _build_scope_plan(resolved: ResolvedProfile, options: CompileOptions) -> ScopePlan:
    """Build the scope seam without mixing it into capability projection."""
    visibility = options.visibility if options.visibility else tuple(Scope)
    return ScopePlan(
        profile_path=resolved.profile_path,
        lifecycle=options.lifecycle,
        visibility=visibility,
        acl_grants=tuple(options.acl_grants),
        budget_ceiling=options.budget_ceiling or BudgetCeiling(),
        revision="v1",
    )


def _require_executable_phase_graph(declarative: DeclarativePlanProjection) -> None:
    """Reject a runnable plan unless every closed-set phase has one binding."""
    present = {binding.semantic_phase for binding in declarative.phase_bindings}
    missing = tuple(phase for phase in SemanticPhase if phase not in present)
    if missing:
        phase_names = ", ".join(phase.value for phase in missing)
        raise PlanCompilerError(
            "runnable declarative profile is missing phase bindings: " + phase_names
        )
    require_valid(declarative.validation_report)


# === Deprecation (ADR-0115) ===
warnings.warn(
    "lca.harness.profile.plan_compiler is deprecated, use lca_kernel.plan_compiler (ADR-0115)",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "CompileOptions",
    "PlanCompilerError",
    "compile_plan",
    "explain_compile_plan",
]
