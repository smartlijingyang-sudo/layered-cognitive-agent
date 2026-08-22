"""PlanCompiler（ADR-0068 §一 + ADR-0074 PR-3）。

``compile_plan()`` 把 ``ResolvedProfile`` 编译为不可变
``CompiledRunPlan = CapabilityPlan + ControlPlan + ScopePlan``：

1. 从 ``ResolvedProfile`` 派生 ``CapabilityPlan``（PR-2.5 resolver）
2. 从 ``ResolvedProfile`` 派生 ``ControlPlan``（PR-1 resolver）
3. 从 profile 顶层 + bundle / patch 提取 ``ScopePlan``（最小版）：
   lifecycle / visibility / acl_grants / budget_ceiling
4. 计算 ``plan_ref``（PR-3 plan_hash determinism property test 守护）

PR-3 阶段：PlanCompiler **不修改** RuntimeKernel，只提供 ``plan_ref``
作为 PR-6 plan_ref × Journal 绑定的基础。

ADR-0074 §3.4 决策（PR-5 contingency）：本文件**不依赖** ADR-0071
Composer-per-Cluster；PlanCompiler 是纯函数（输入 ResolvedProfile →
输出 CompiledRunPlan），可独立测试。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.plan import (
    COMPILED_RUN_PLAN_VERSION,
    CompiledRunPlan,
    build_input_provenance,
    capability_sub_plan_hash,
    compiled_run_plan_ref,
    control_sub_plan_hash,
    scope_sub_plan_hash,
)
from lca.contracts.protocols.scope_plan import BudgetCeiling, ScopePlan
from lca.harness.declarative.compiler import compile_declarative_projection
from lca.harness.profile.capability_plan_resolver import (
    CapabilityPlanOptions,
    project_capability_plan,
)
from lca.harness.profile.control_plan_resolver import (
    ControlPlanOptions,
    project_control_plan,
)
from lca.harness.profile.resolve import ResolvedProfile


class PlanCompilerError(ValueError):
    """PlanCompiler 编译失败（profile 不合法 / 子 plan 投影失败）。"""


@dataclass(frozen=True, slots=True)
class CompileOptions:
    """PlanCompiler 编译选项。

    - ``lifecycle`` — plan 生命周期 scope（默认 = ``run``）
    - ``visibility`` — plan 可见性 scope 集合（默认 = 全 8 scope）
    - ``acl_grants`` — capability grant ceiling 列表
    - ``budget_ceiling`` — BudgetCeiling（默认 = 不限制）
    - ``task_id`` — task contract id（用于 input_provenance）
    - ``env_fingerprint`` — 环境指纹（env hash，跨进程稳定）
    - ``include_disabled`` — 是否包含 disabled plugin
    """

    lifecycle: Scope = Scope.RUN
    visibility: tuple[Scope, ...] = ()
    acl_grants: tuple[str, ...] = ()
    budget_ceiling: BudgetCeiling | None = None
    task_id: str | None = None
    env_fingerprint: str | None = None
    include_disabled: bool = False


def compile_plan(
    resolved: ResolvedProfile,
    *,
    options: CompileOptions | None = None,
) -> CompiledRunPlan:
    """Compile ``ResolvedProfile`` → ``CompiledRunPlan``。

    步骤：

    1. 投影 ``CapabilityPlan``（含 provider_bindings + 11 关系）
    2. 投影 ``ControlPlan``（含 11 槽位 entries）
    3. 构造 ``ScopePlan``（最小版：lifecycle + visibility + ACL + budget）
    4. 计算 ``plan_ref``（cross-process / cross-run 稳定）

    返回 immutable ``CompiledRunPlan``；可由 ``compiled_run_plan_ref()``
    取得 plan_ref 字符串用于 PR-6 plan_ref × Journal 绑定。
    """
    opts = options or CompileOptions()
    cap_options = CapabilityPlanOptions(include_disabled=opts.include_disabled)
    ctrl_options = ControlPlanOptions(include_disabled=opts.include_disabled)

    capability = project_capability_plan(resolved, options=cap_options)
    control = project_control_plan(resolved, options=ctrl_options)

    # visibility 默认 = 所有 Scope（8 项）
    visibility = opts.visibility if opts.visibility else tuple(Scope)
    budget = opts.budget_ceiling or BudgetCeiling()

    scope = ScopePlan(
        profile_path=resolved.profile_path,
        lifecycle=opts.lifecycle,
        visibility=visibility,
        acl_grants=tuple(opts.acl_grants),
        budget_ceiling=budget,
        revision="v1",
    )

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
    )
    declarative.validation_report.require_valid()

    return CompiledRunPlan(
        profile_path=resolved.profile_path,
        capability=capability,
        control=control,
        scope=scope,
        plan_version=COMPILED_RUN_PLAN_VERSION,
        input_provenance=input_provenance,
        revision="v2",
        plugin_specs=declarative.plugin_specs,
        capability_bindings=declarative.capability_bindings,
        phase_graph=declarative.phase_graph,
        phase_bindings=declarative.phase_bindings,
        control_entries=declarative.control_entries,
        replacement_map=declarative.replacement_map,
        effect_policy=declarative.effect_policy,
        provenance=declarative.provenance,
        validation_report=declarative.validation_report,
    )


def explain_compile_plan(plan: CompiledRunPlan) -> dict[str, Any]:
    """``lca-ops plan inspect <profile>`` 的最小输出（PR-3）。"""
    return {
        "profile_path": plan.profile_path,
        "plan_ref": compiled_run_plan_ref(plan),
        "plan_version": plan.plan_version,
        "revision": plan.revision,
        "input_provenance": [{"kind": kind, "path": path} for kind, path in plan.input_provenance],
        "declarative": {
            "schema_version": plan.schema_version,
            "plugin_count": len(plan.plugin_specs),
            "phase_nodes": len(plan.phase_graph.nodes) if plan.phase_graph else 0,
            "phase_bindings": [
                {
                    "node": binding.node_id,
                    "phase": binding.semantic_phase.value,
                    "executor": binding.executor_capability,
                    "contributions": [contribution.executor for contribution in binding.contributions],
                }
                for binding in plan.phase_bindings
            ],
            "replacement_map": [
                {"target": item.target, "winner": item.winner, "mode": item.mode, "reason": item.reason}
                for item in plan.replacement_map
            ],
            "effect_policy": {
                "gateway": plan.effect_policy.gateway_capability if plan.effect_policy else "",
                "allowed_effects": list(plan.effect_policy.allowed_effects) if plan.effect_policy else [],
            },
            "validation": {
                "valid": plan.validation_report.is_valid,
                "errors": [issue.code for issue in plan.validation_report.errors],
            },
        },
        "sub_plans": {
            "capability": {
                "plan_hash": capability_sub_plan_hash(plan),
                "binding_count": len(plan.capability.provider_bindings),
                "relation_count": len(plan.capability.relations),
            },
            "control": {
                "plan_hash": control_sub_plan_hash(plan),
                "entry_count": len(plan.control.entries),
                "covered_slots": sorted(s.value for s in plan.control.by_slot),
            },
            "scope": {
                "plan_hash": scope_sub_plan_hash(plan),
                "lifecycle": plan.scope.lifecycle.value,
                "visibility": [s.value for s in plan.scope.visibility],
                "acl_grants": list(plan.scope.acl_grants),
            },
        },
    }


__all__ = [
    "CompileOptions",
    "PlanCompilerError",
    "compile_plan",
    "explain_compile_plan",
]
