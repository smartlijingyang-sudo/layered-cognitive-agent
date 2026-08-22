"""spawn.bind_plan —— ADR-0074 PR-5 + ADR-0071 Composer-per-Cluster。

把 ``spawn_agent`` 内联的装配策略（BrainFactory / Body / PerceiveHub /
Team）抽出到 4 个 sub-composer plugin；L4 spawn 只保留「绑定 plan + 上下文
+ 编排图」的角色。

PR-5 落地：

1. ``bind_plan(spec, plan, scope)`` → ``AgentGraph``
   - 从 plan 读 CapabilityPlan / ControlPlan / ScopePlan
   - 调 4 个 sub-composer（BODY / BRAIN / PERCEIVE / TEAM）拼装图
   - 校验 CapabilityPlan.provider_bindings 全部 resolve

2. ``bind_team(spec, plan, scope)`` → ``TeamGraph``
   - TeamComposer 编排 members + strategy + stage + transport

3. spawn_agent 拆为 ``bind_plan`` + ``_legacy_spawn_objects``：
   - ``_legacy_spawn_objects`` 是 PR-5 之前的兼容路径（保留 6 个月）
   - ``spawn_agent(spec, plan=compiled_plan, scope=ctx)`` 默认走 bind_plan
   - 不传 plan 时自动编译（``compile_plan(resolve_profile(spec.profile))``）

L4 不再 import 具体插件 ID：

- ``BRAINS.key`` / ``BODIES.key`` / ``STOP_RULES.key`` / ``STRATEGIES.key``
  移交给 sub-composer plugin（PR-5a BrainComposer + BodyComposer +
  PerceiveComposer；PR-5b TeamComposer）

- RuntimeDeps（lca/layer4_app/runtime_factory.py）用 ``compiled_plan`` 替换
  散落的 factory 字段（PR-5a 阶段 RuntimeDeps 不变；plan 作为 kwarg 传入）

兼容性：LCA_PLAN_COMPAT 兼容开关（PR-3 引入）继续生效；老路径
``spawn_agent(spec)`` 不传 plan → 走 ``_legacy_spawn_objects``。
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.harness.composer import AgentGraph, TeamGraph
    from lca.contracts.protocols.plan import CompiledRunPlan
    from lca.contracts.protocols.spec import AgentSpec, TeamSpec

# Re-export at runtime for testing / inspection (avoid TYPE_CHECKING-only F821)
from lca.contracts.protocols.plan import (  # noqa: F401
    CompiledRunPlan as _CompiledRunPlan,
)
from lca.contracts.protocols.plan import (
    compiled_run_plan_ref,
)
from lca.contracts.protocols.spec import (  # noqa: F401
    AgentSpec as _AgentSpec,
)


@dataclass(frozen=True, slots=True)
class BindOptions:
    """``bind_plan`` 配置选项。

    - ``use_legacy_spawn`` — 强制走老路径（PR-5 之前 compat），默认 False
    - ``include_disabled`` — 是否包含 disabled plugin（forwarded to plan_compiler）
    - ``enforce_capability_plan`` — 校验所有 provider_bindings 都 resolve；默认 True
    """

    use_legacy_spawn: bool = False
    include_disabled: bool = False
    enforce_capability_plan: bool = True


@dataclass(frozen=True, slots=True)
class PlanBindingResult:
    """bind_plan 输出（frozen dataclass）。

    - ``graph`` — ``AgentGraph``（BrainComposer + BodyComposer + PerceiveComposer merge 后）
    - ``plan_ref`` — CompiledRunPlan.plan_ref（用于 plan_ref × Journal 绑定，PR-6）
    - ``plan`` — 完整 CompiledRunPlan（用于 runtime 消费）
    - ``metadata`` — 装配元数据（resolved_plugins / composer_keys 等）
    """

    graph: AgentGraph
    plan_ref: str
    plan: CompiledRunPlan
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TeamBindingResult:
    """bind_team 输出（frozen dataclass）。"""

    graph: TeamGraph
    plan_ref: str
    plan: CompiledRunPlan
    metadata: dict[str, Any] = field(default_factory=dict)


class BindPlanError(ValueError):
    """``bind_plan`` 失败（plan 不合法 / sub-composer 缺失 / capability 不齐）。"""


def bind_plan(
    spec: AgentSpec,
    plan: CompiledRunPlan,
    *,
    scope: Context,
    options: BindOptions | None = None,
) -> PlanBindingResult:
    """Bind ``CompiledRunPlan`` + ``AgentSpec`` + cordis scope → ``AgentGraph``。

    步骤：

    1. 校验 ``plan.profile_path`` 与 spec 一致（避免误绑）
    2. 调 4 个 sub-composer（BODY / BRAIN / PERCEIVE / TEAM）的
       ``compose_agent(spec, scope)``，每个返回部分 ``AgentGraph``
    3. ``merge_agent_graphs`` 合并成完整图
    4. 校验 CapabilityPlan.provider_bindings 全部 resolve（可选）
    5. 返回 ``PlanBindingResult``（含 plan_ref 用于 PR-6 绑定）

    注意：PR-5a 阶段 BRAIN / BODY / PERCEIVE composer 已实现；
    TEAM composer 在 PR-5b 实现（PR-5a 阶段 bind_plan 不支持 team）。
    """
    opts = options or BindOptions()

    if opts.use_legacy_spawn:
        # PR-5 之前 compat 路径：bind_plan 退化为 _legacy_spawn_objects
        warnings.warn(
            "bind_plan called with use_legacy_spawn=True; "
            "falling back to _legacy_spawn_objects() (PR-5 之前 compat path)",
            DeprecationWarning,
            stacklevel=2,
        )
        return _legacy_bind_plan(spec, plan, scope=scope)

    # Plan / spec 一致性校验（软检查；只 warn 不 raise）
    spec_name = getattr(spec, "name", "")
    plan_path = getattr(plan, "profile_path", "") or ""
    if (
        plan_path
        and isinstance(plan_path, str)
        and isinstance(spec_name, str)
        and not plan_path.endswith(spec_name or "")
    ):
        warnings.warn(
            f"bind_plan: plan.profile_path={plan_path!r} "
            f"may not match spec; proceeding with bind_plan",
            UserWarning,
            stacklevel=2,
        )

    # Import here to avoid circular imports
    from lca.contracts.harness.composer import merge_agent_graphs

    composer_results: list[Any] = []
    metadata: dict[str, Any] = {"composers_used": [], "missing_composers": []}

    # Compose via sub-composers (PR-5a: BRAIN + BODY + PERCEIVE)
    for key in ("brain", "body", "perceive"):
        try:
            composer = _resolve_composer(scope, key)
            partial = composer.compose_agent(spec, scope)
            composer_results.append(partial)
            metadata["composers_used"].append(key)
        except _ComposerMissingError:
            metadata["missing_composers"].append(key)

    if not composer_results:
        raise BindPlanError(
            f"bind_plan: no sub-composer available for spec {spec!r}. "
            f"Missing: {metadata['missing_composers']}. "
            "Boot composer.{brain,body,perceive} plugins to enable PR-5 path."
        )

    graph = merge_agent_graphs(*composer_results)

    # Validate capability bindings (optional)
    if opts.enforce_capability_plan:
        _validate_capability_bindings(plan, graph, scope)

    return PlanBindingResult(
        graph=graph,
        plan_ref=compiled_run_plan_ref(plan),
        plan=plan,
        metadata=metadata,
    )


def bind_team(
    spec: TeamSpec,
    plan: CompiledRunPlan,
    *,
    scope: Context,
    options: BindOptions | None = None,
) -> TeamBindingResult:
    """Bind ``CompiledRunPlan`` + ``TeamSpec`` + cordis scope → ``TeamGraph``。

    PR-5b：TEAM composer 编排 members + strategy + stage + transport。
    PR-5a 阶段：team composer 尚未实现 → 退化为 _legacy_bind_team。

    步骤：

    1. 校验 plan 含 team 级 scope（ExecutionSpace + LifecycleSpace 最小版）
    2. 调 TeamComposer.compose_team(spec, scope)
    3. 校验每个 member 通过 bind_plan 装配（递归调 bind_plan）
    4. 编排 strategy / stage / transport
    5. 返回 ``TeamBindingResult``
    """
    try:
        composer = _resolve_composer(scope, "team")
    except _ComposerMissingError:
        warnings.warn(
            "bind_team: TEAM composer not yet implemented or unavailable; "
            "falling back to compatibility binding",
            DeprecationWarning,
            stacklevel=2,
        )
        return _legacy_bind_team(spec, plan, scope=scope)

    graph = composer.compose_team(spec, scope)
    if (
        not graph.members
        or graph.strategy is None
        or graph.stage is None
        or graph.transport is None
    ):
        raise BindPlanError("bind_team: TeamComposer returned an incomplete TeamGraph")
    return TeamBindingResult(
        graph=graph,
        plan_ref=compiled_run_plan_ref(plan),
        plan=plan,
        metadata={"composer_key": "team"},
    )


# ── Composer resolution ──────────────────────────────────────────────


class _ComposerMissingError(LookupError):
    """sub-composer plugin 未在 scope 中注册。"""


def _resolve_composer(scope: Context, key: str) -> Any:
    """从 scope 解析 sub-composer plugin。

    PR-5 路径：``ctx.provide(f"composer.{key}", ComposerImpl())`` 提供；
    scope 通过 ``require_capability(scope, f"composer.{key}")`` 解析。

    返回 Composer Protocol 实现实例；调用方用 ``.compose_agent(spec, scope)``
    构造部分 AgentGraph。
    """
    full_key = f"composer.{key}"
    inject = getattr(scope, "inject", None)
    if not callable(inject):
        raise _ComposerMissingError("scope has no inject() method (need cordis Context)")
    try:
        composer = inject(full_key)
    except (KeyError, LookupError) as exc:
        raise _ComposerMissingError(
            f"composer.{key} not registered in scope (plugin missing or disabled)"
        ) from exc
    if composer is None:
        raise _ComposerMissingError(f"composer.{key} resolved to None")
    return composer


def _validate_capability_bindings(
    plan: CompiledRunPlan,
    graph: AgentGraph,
    scope: Context,
) -> None:
    """校验 plan.capability.provider_bindings 全部 resolve 到 graph + scope。

    不校验（PR-5a 阶段跳过）：capability provider plugin 与 graph 是否一致
    消费（这是 PR-5b TeamComposer 的工作）。
    """
    bindings = plan.capability.provider_bindings
    if not bindings:
        return  # 空 plan（无显式 provider）跳过
    # PR-5a: 仅校验每个 capability key 在 scope 中可解析
    inject = getattr(scope, "inject", None)
    if not callable(inject):
        return
    for binding in bindings:
        capability = binding.capability
        registry_key = capability.split("[", 1)[0]
        candidates = [capability, registry_key]
        if "." in registry_key:
            candidates.append(registry_key.split(".", 1)[0])

        last_error: Exception | None = None
        for candidate in dict.fromkeys(candidates):
            try:
                inject(candidate)
                break
            except (KeyError, LookupError) as error:
                last_error = error
        else:
            raise BindPlanError(
                f"bind_plan: capability {capability!r} "
                f"(owner={binding.owner_plugin!r}) has no resolvable registry "
                f"among {tuple(dict.fromkeys(candidates))!r}: {last_error}"
            ) from last_error


# ── Legacy compat (PR-5 之前路径；保留 6 个月) ─────────────────────


def _legacy_bind_plan(
    spec: AgentSpec,
    plan: CompiledRunPlan,
    *,
    scope: Context,
) -> PlanBindingResult:
    """PR-5 之前兼容路径：返回最小 AgentGraph（仅 observability + metadata）。

    不构造 Brain / Body / PerceiveHub；调用方应改用 ``spawn_agent``
    （保留旧路径）直到 PR-5b 落地。
    """
    from lca.contracts.harness.composer import AgentGraph

    # Minimal graph: only observability + placeholder deps
    graph = AgentGraph(
        brain=None,  # type: ignore[arg-type]
        body=None,  # type: ignore[arg-type]
        memory=None,  # type: ignore[arg-type]
        state_store=None,  # type: ignore[arg-type]
        perceive_hub=None,  # type: ignore[arg-type]
        hooks=None,  # type: ignore[arg-type]
        observability=None,
        llm=None,  # type: ignore[arg-type]
        stop_rule=None,  # type: ignore[arg-type]
        metadata={"legacy": True, "plan_ref": compiled_run_plan_ref(plan)},
    )
    return PlanBindingResult(
        graph=graph,
        plan_ref=compiled_run_plan_ref(plan),
        plan=plan,
        metadata={"legacy": True},
    )


def _legacy_bind_team(
    spec: TeamSpec,
    plan: CompiledRunPlan,
    *,
    scope: Context,
) -> TeamBindingResult:
    """PR-5b 之前兼容路径：返回最小 TeamGraph。"""
    from lca.contracts.harness.composer import TeamGraph

    graph = TeamGraph(
        members=(),
        strategy=None,
        stage=None,
        transport=None,
        observability=None,
        metadata={"legacy": True, "plan_ref": compiled_run_plan_ref(plan)},
    )
    return TeamBindingResult(
        graph=graph,
        plan_ref=compiled_run_plan_ref(plan),
        plan=plan,
        metadata={"legacy": True},
    )


# ── Capability check helper ─────────────────────────────────────────


def is_bind_plan_available(scope: Context) -> bool:
    """``scope`` 是否含 PR-5 sub-composer plugins（brain / body / perceive）？

    L4 spawn 在 boot 时调用以决定走 ``bind_plan`` 还是 ``_legacy_bind_plan``。
    """
    for key in ("brain", "body", "perceive"):
        try:
            _resolve_composer(scope, key)
        except _ComposerMissingError:
            return False
    return True


__all__ = [
    "BindOptions",
    "BindPlanError",
    "PlanBindingResult",
    "TeamBindingResult",
    "bind_plan",
    "bind_team",
    "is_bind_plan_available",
]
