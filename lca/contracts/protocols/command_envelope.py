"""CommandEnvelope + RunFact 数据契约（ADR-0068 §一 + ADR-0074 PR-7）。

CommandEnvelope 是外部世界 effect 的**唯一入口**（ADR-0068 §五）；
Decision 不是 Command。任何 effect 必须经过：

    decision → mint_envelope() → authorize → budget → constrain → execute → safe-boundary

字段：

- ``plan_ref`` — CompiledRunPlan canonical hash（PR-6 V5 守护）
- ``scope_ref`` — ExecutionSpace / LifecycleSpace scope identifier
- ``decision_ref`` — 触发该 envelope 的 Decision 的全局唯一 id
- ``provider`` — 选中的 tool / executor provider name（regid 或 plugin id）
- ``grant`` — capability grant ceiling（V8 单调：子 ⊆ 父）
- ``budget_reservation`` — 调用前从 budget.snapshot 扣减的预算
- ``idempotency_key`` — 同决策 + 同参数 → 同 key，用于 retry / cache 去重
- ``policy_verdict_refs`` — 经 5 闸单调聚合后的 policy fact 引用 tuple
- ``execution_space_ref`` — 执行空间引用（plan.scope.execution_space）

PR-7 阶段：mint_envelope factory + dataclass；5 闸单调聚合（authorize /
budget / constrain / execute / safe-boundary）的 runtime 接线在 PR-7
后段 / PR-8 落地（PR-7 主要交付数据面 + AST architecture test 守护）。

ADR-0015 contracts 纯类型契约：CommandEnvelope 不放方法，访问器
module-level 函数（``command_envelope_to_dict`` / ``envelope_is_authorized``）。

不变量（ADR-0068 §五）：

1. authority 仅可向子 scope 衰减（V8）
2. world effect 仅可经 G7 的 CommandEnvelope 穿出
3. envelope 不可在 runtime mutate；重新编 plan → 新 envelope
4. policy_verdict_refs 在 5 闸单调聚合后写入；不允许后续修改
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EnvelopeVerdict(str, Enum):
    """5 闸单调聚合后的 envelope 状态（PR-7 数据面）。"""

    AUTHORIZED = "authorized"
    DENIED = "denied"
    """任一闸拒绝；V4 acceptance: envelope.mint 在 stack trace。"""
    BUDGET_EXHAUSTED = "budget_exhausted"
    CONSTRAINT_VIOLATED = "constraint_violated"
    SAFE_BOUNDARY_VIOLATED = "safe_boundary_violated"


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    """调用前从 budget.snapshot 扣减的预算（PR-7 数据面）。

    5 闸单调聚合：任一闸拒绝 → reservation 立即释放；不影响后续 envelope。
    """

    tokens: int = 0
    cost_cents: int = 0
    wall_clock_ms: int = 0
    tool_calls: int = 0


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    """capability grant ceiling（V8 单调：子 ⊆ 父）。

    PR-7 阶段：单层 grant；嵌套授权树（grant tree）由 PR-8 落地。
    """

    capability: str = ""
    scope: str = ""  # release / profile / agent / run / turn / invocation / experiment / device
    effect_class: str = "none"


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    """外部世界 effect 唯一入口（ADR-0068 §五 + ADR-0074 PR-7 V4 hard constraint）。

    任何外部 effect（tool call / HTTP / sandbox / A2A transport）必须经
    CommandEnvelope 走 5 闸单调聚合。Decision 不是 Command —— Decision
    是意图；CommandEnvelope 是意图 + grant + budget + verdict refs 的
    可执行封套。
    """

    plan_ref: str = ""
    """CompiledRunPlan canonical hash（PR-6 V5）。"""
    scope_ref: str = ""
    """ExecutionSpace / LifecycleSpace scope identifier。"""
    decision_ref: str = ""
    """触发该 envelope 的 Decision 全局唯一 id（call_id）。"""
    provider: str = ""
    """选中的 tool / executor provider name（plugin id）。"""
    grant: CapabilityGrant = field(default_factory=CapabilityGrant)
    """capability grant ceiling（V8 单调）。"""
    budget_reservation: BudgetReservation = field(default_factory=BudgetReservation)
    """调用前从 budget.snapshot 扣减的预算。"""
    idempotency_key: str = ""
    """同 decision + 同参数 → 同 key（用于 retry / cache 去重）。"""
    policy_verdict_refs: tuple[str, ...] = ()
    """5 闸单调聚合后的 policy fact 引用 tuple。"""
    execution_space_ref: str = ""
    """执行空间引用（plan.scope.execution_space 字段；PR-7 阶段暂留空）。"""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    """插件可扩展字段（不破坏核心元数据）。"""
    version: int = 1
    """envelope 自身版本号；schema 变更 +1。"""

    def __post_init__(self) -> None:
        if not isinstance(self.grant, CapabilityGrant):
            object.__setattr__(self, "grant", CapabilityGrant(**dict(self.grant)))
        if not isinstance(self.budget_reservation, BudgetReservation):
            object.__setattr__(
                self,
                "budget_reservation",
                BudgetReservation(**dict(self.budget_reservation)),
            )
        if not isinstance(self.policy_verdict_refs, tuple):
            object.__setattr__(self, "policy_verdict_refs", tuple(self.policy_verdict_refs))
        if not isinstance(self.metadata, Mapping):
            # accept plain dict via Mapping normalization
            object.__setattr__(self, "metadata", dict(self.metadata))


# ── RunFact / RunDelta / Verdict (union types) ────────────────────────


@dataclass(frozen=True, slots=True)
class RunFact:
    """Run-level 事实（PR-7 数据面）。

    与 JournalEvent 不同：RunFact 是 **内部 Run 状态机的 typed 事件**，
    用于 reducer / state machine；JournalEvent 是 **append-only 解释平面**
    （PR-6 V5 守护 plan_ref）。两者正交。

    PR-7 阶段：RunFact 是 dataclass 集合；reducer 转换 / sequence 编排
    留 PR-8 落地。
    """

    fact_id: str = ""
    plan_ref: str = ""
    kind: str = ""  # "tool_invoked" / "policy_denied" / "budget_exhausted" / "decision_made" / etc.
    payload: Mapping[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


@dataclass(frozen=True, slots=True)
class RunDelta:
    """State mutation delta（PR-7 数据面 + ADR-0070 Reducer 协议）。

    Reducer 协议（lca/contracts/protocols/reducer.py）的输入；RunDelta
    是 apply_* 方法接收的事实包装。RunDelta.facts 累积 1..N RunFact，
    reducer 输出新 AgentState。

    PR-7 阶段：RunDelta 数据面 + reducer fold 集成；runtime wiring
    （RunStore.append ↔ reducer.apply_*）留 PR-8。
    """

    plan_ref: str = ""
    run_id: str = ""
    facts: tuple[RunFact, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


class Verdict(str, Enum):
    """5 闸单调聚合后的最终 verdict（PR-7 数据面 + ADR-0066 §四）。

    单调性：DENIED > BUDGET_EXHAUSTED > CONSTRAINT_VIOLATED > SAFE_BOUNDARY_VIOLATED >
    AUTHORIZED（higher = more restrictive）。任意一闸拒绝 → verdict 不被
    后续闸覆盖。
    """

    AUTHORIZED = "authorized"
    DENIED = "denied"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CONSTRAINT_VIOLATED = "constraint_violated"
    SAFE_BOUNDARY_VIOLATED = "safe_boundary_violated"


@dataclass(frozen=True, slots=True)
class DecisionRef:
    """Decision 引用（轻量；避免 envelope 持有完整 Decision 对象）。

    PR-7 阶段：仅持有 decision_id + plan_ref + scope_ref；完整 Decision
    通过 reducer.apply_turn 折叠到 state.history。
    """

    decision_id: str = ""
    plan_ref: str = ""
    scope_ref: str = ""
    action_type: str = ""
    tool_name: str = ""


# ── Module-level accessors / factories (ADR-0015) ───────────────────


def mint_envelope(
    *,
    plan_ref: str,
    scope_ref: str,
    decision: Any,
    provider: str,
    grant: Any | None = None,
    budget_reservation: Any | None = None,
    idempotency_key: str = "",
    policy_verdict_refs: tuple[str, ...] = (),
    execution_space_ref: str = "",
    metadata: Mapping[str, Any] | None = None,
    version: int = 1,
) -> CommandEnvelope:
    """Mint CommandEnvelope factory（PR-7 V4 acceptance 守护）。

    architecture test (scripts/check_command_envelope_required.py) 守护：
    ``pipeline_safe_executor.execute`` 的 stack trace 必须含本函数。

    Args:
        plan_ref: CompiledRunPlan canonical hash (PR-6 V5)
        scope_ref: ExecutionSpace / LifecycleSpace scope identifier
        decision: Decision 对象 / DecisionRef / 任意带 ``decision_id`` 字段的对象
        provider: tool / executor provider name (plugin id)
        grant: CapabilityGrant 或 dict；None → 默认空 grant
        budget_reservation: BudgetReservation 或 dict；None → 默认空 reservation
        idempotency_key: 同 decision + 同参数 → 同 key（去重）
        policy_verdict_refs: tuple of policy fact refs（5 闸聚合后）
        execution_space_ref: plan.scope.execution_space 字段引用
        metadata: 插件可扩展字段
        version: envelope schema 版本号
    """
    if not plan_ref:
        raise ValueError("mint_envelope: plan_ref must be non-empty string (V5)")
    if not scope_ref:
        raise ValueError("mint_envelope: scope_ref must be non-empty string")
    if not provider:
        raise ValueError("mint_envelope: provider must be non-empty string")

    # decision may be Decision object, DecisionRef, dict, or any object with decision_id
    if isinstance(decision, dict):
        decision_id = str(decision.get("decision_id", "") or decision.get("id", "") or "")
    else:
        decision_id = str(getattr(decision, "decision_id", "") or getattr(decision, "id", "") or "")

    return CommandEnvelope(
        plan_ref=plan_ref,
        scope_ref=scope_ref,
        decision_ref=decision_id,
        provider=provider,
        grant=grant or CapabilityGrant(),
        budget_reservation=budget_reservation or BudgetReservation(),
        idempotency_key=idempotency_key,
        policy_verdict_refs=policy_verdict_refs,
        execution_space_ref=execution_space_ref,
        metadata=metadata or {},
        version=version,
    )


def command_envelope_to_dict(envelope: CommandEnvelope) -> dict[str, Any]:
    """JSON 友好字典（PR-7 V4 architecture test 输出）。"""
    return {
        "plan_ref": envelope.plan_ref,
        "scope_ref": envelope.scope_ref,
        "decision_ref": envelope.decision_ref,
        "provider": envelope.provider,
        "grant": {
            "capability": envelope.grant.capability,
            "scope": envelope.grant.scope,
            "effect_class": envelope.grant.effect_class,
        },
        "budget_reservation": {
            "tokens": envelope.budget_reservation.tokens,
            "cost_cents": envelope.budget_reservation.cost_cents,
            "wall_clock_ms": envelope.budget_reservation.wall_clock_ms,
            "tool_calls": envelope.budget_reservation.tool_calls,
        },
        "idempotency_key": envelope.idempotency_key,
        "policy_verdict_refs": list(envelope.policy_verdict_refs),
        "execution_space_ref": envelope.execution_space_ref,
        "metadata": dict(envelope.metadata),
        "version": envelope.version,
    }


def envelope_is_authorized(envelope: CommandEnvelope) -> bool:
    """envelope 是否已授权（policy_verdict_refs 非空 = 通过 5 闸聚合）。"""
    return len(envelope.policy_verdict_refs) > 0


def envelope_aggregate_verdict(envelope: CommandEnvelope) -> Verdict:
    """5 闸单调聚合后的最终 verdict（PR-7 数据面 + ADR-0066 §四）。

    聚合规则：
    - 任一闸拒绝 → 不被后续闸覆盖（单调）
    - 优先级（PR-7 阶段）：SAFE_BOUNDARY_VIOLATED > CONSTRAINT_VIOLATED >
      BUDGET_EXHAUSTED > DENIED > AUTHORIZED
    - 当前 verdict 来自 envelope.policy_verdict_refs 的 policy fact 字段
      （PR-7 阶段：简化为「非空 = AUTHORIZED」；PR-8 接入 5 闸实际 verdict）
    """
    if envelope_is_authorized(envelope):
        return Verdict.AUTHORIZED
    # PR-7 阶段：未授权 = 默认 DENIED（PR-8 细分 5 闸）
    return Verdict.DENIED


def warn_deprecated_envelope_constructor(envelope: CommandEnvelope) -> None:
    """PR-7 数据面落地的 deprecation warning — 不直接构造 CommandEnvelope。"""
    warnings.warn(
        "Direct CommandEnvelope construction is deprecated (PR-7); "
        "use mint_envelope() factory instead. Direct construction will be "
        "removed in PR-8 (architecture test gate).",
        DeprecationWarning,
        stacklevel=3,
    )


__all__ = [
    "BudgetReservation",
    "CapabilityGrant",
    "CommandEnvelope",
    "DecisionRef",
    "EnvelopeVerdict",
    "RunDelta",
    "RunFact",
    "Verdict",
    "command_envelope_to_dict",
    "envelope_aggregate_verdict",
    "envelope_is_authorized",
    "mint_envelope",
    "warn_deprecated_envelope_constructor",
]
