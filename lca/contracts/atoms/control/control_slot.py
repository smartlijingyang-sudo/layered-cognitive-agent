"""控制槽位有限枚举（ADR-0066 §二 + tracker §19）。

控制槽位是 LCA 控制面单一入口（ADR-0066 §四单调聚合 + ADR-0074 §一接受
9 槽 + 2 横切项 = 11 槽）。所有可独立启停、可独立授权、可独立审计的
harness 行为——budget / authorize / constrain / guard / stop / admit /
observe / checkpoint / safe-boundary——必须以最小插件或插件组贡献的
形式声明并组合；六步认知循环、类型契约、Reducer 单写状态、Journal
提交边界与执行窄门仍是不可由配置改写的宪法。

枚举值字符串与原始 ADR 表述一致，保证序列化 / 反序列化兼容。
``slot_pattern`` 提供 ``observe.*`` 的语义壳（运行时不可枚举其子项，
新增观察口需 ADR）。
"""

from __future__ import annotations

from enum import Enum


class ControlSlot(str, Enum):
    """有限、类型化的 Control Slot（ADR-0066 §二 + tracker §19）。

    11 个槽位：

    1. ``perceive.context`` —— 外部事实成为可信 context（Perceive 阶段）
    2. ``think.guard`` —— 决策的确定性治理（Think / Gate 阶段）
    3. ``act.authorize`` —— 执行授权（Act / Execution Control）
    4. ``act.budget`` —— 预算检查（Act / Execution Control）
    5. ``act.constrain`` —— 策略约束（Act / Execution Control）
    6. ``act.execute`` —— 安全执行（Body / SafeExecutor）
    7. ``act.safe-boundary`` —— effect dispatch 最后一道物理隔离闸
       （ADR-0074 tracker §19 由 ADR-0068 §三 ``safe-boundary`` 横切项挂入）
    8. ``remember.admit`` —— 记忆准入（Memory 阶段）
    9. ``stop.decide`` —— 停止判定（Stop 阶段）
    10. ``observe.checkpoint`` —— 可观察 checkpoint 事件
        （ADR-0074 tracker §19 由 ADR-0068 §三 ``checkpoint`` 横切项挂入）
    11. ``observe.*`` —— 通用观察口语义壳（metrics / trace / debug）

    新增第 12 槽位需 ADR 或对相应原语协议的审查；插件只能向现有
    槽位投稿，不能以字符串临时发明 ``agent.before_everything``。
    """

    PERCEIVE_CONTEXT = "perceive.context"
    THINK_GUARD = "think.guard"
    ACT_AUTHORIZE = "act.authorize"
    ACT_BUDGET = "act.budget"
    ACT_CONSTRAIN = "act.constrain"
    ACT_EXECUTE = "act.execute"
    ACT_SAFE_BOUNDARY = "act.safe-boundary"
    REMEMBER_ADMIT = "remember.admit"
    STOP_DECIDE = "stop.decide"
    OBSERVE_CHECKPOINT = "observe.checkpoint"
    OBSERVE_WILDCARD = "observe.*"


# ── Pattern handling ────────────────────────────────────────────
# ``observe.*`` is a semantic wildcard covering concrete observability
# slots that don't have a fixed contract (metrics, trace, debug). It is
# kept as an explicit enum member so profile linters see it, but it is
# excluded from ``phase_owner`` lookups below — concrete observe slots
# resolve to ``None`` for phase.

SLOT_PHASE_OWNER: dict[ControlSlot, str | None] = {
    ControlSlot.PERCEIVE_CONTEXT: "perceive",
    ControlSlot.THINK_GUARD: "think",
    ControlSlot.ACT_AUTHORIZE: "act",
    ControlSlot.ACT_BUDGET: "act",
    ControlSlot.ACT_CONSTRAIN: "act",
    ControlSlot.ACT_EXECUTE: "act",
    ControlSlot.ACT_SAFE_BOUNDARY: "act",
    ControlSlot.REMEMBER_ADMIT: "memory",
    ControlSlot.STOP_DECIDE: "stop",
    ControlSlot.OBSERVE_CHECKPOINT: None,  # cross-cutting observer slot
    ControlSlot.OBSERVE_WILDCARD: None,  # semantic wildcard
}
"""slot → C1 阶段归属（v3 宪法 §3.2 六步闭集）；None = 横切观察口。

tracker §19.1 决策记录：

- ``journal.commit`` 不新增 Slot（v3 §6 Journal-as-Truth + ADR-0065 承接）
- ``checkpoint`` 挂 ``observe.checkpoint``
- ``safe-boundary`` 挂 ``act.safe-boundary``（act.execute 后置闸）
"""


def phase_owner(slot: ControlSlot) -> str | None:
    """ControlSlot 的 C1 阶段归属；横切观察口返回 ``None``。

    >>> phase_owner(ControlSlot.ACT_EXECUTE)
    'act'
    >>> phase_owner(ControlSlot.OBSERVE_CHECKPOINT) is None
    True
    """
    return SLOT_PHASE_OWNER[slot]


def is_cross_cutting(slot: ControlSlot) -> bool:
    """是否横切观察口（不属于 C1 阶段）。

    >>> is_cross_cutting(ControlSlot.OBSERVE_WILDCARD)
    True
    >>> is_cross_cutting(ControlSlot.ACT_EXECUTE)
    False
    """
    return SLOT_PHASE_OWNER[slot] is None


def as_phase_label(slot: ControlSlot) -> str:
    """稳定阶段标签（横切口 = ``observe``）。"""
    owner = phase_owner(slot)
    if owner is None:
        return "observe"
    return owner


def parse_slot(value: object) -> ControlSlot:
    """字符串 → ControlSlot。值未匹配 → ``ValueError``。

    接受已为 ``ControlSlot`` 实例的输入（幂等）。
    """
    if isinstance(value, ControlSlot):
        return value
    if isinstance(value, str):
        try:
            return ControlSlot(value)
        except ValueError as exc:
            raise ValueError(
                f"unknown control slot {value!r}; valid: {[s.value for s in ControlSlot]}"
            ) from exc
    raise TypeError(f"control slot must be str or ControlSlot, got {type(value).__name__}")


def all_slot_values() -> tuple[str, ...]:
    """全部槽位字符串值（顺序确定）。"""
    return tuple(s.value for s in ControlSlot)


def validate_slot_iterable(values: object) -> tuple[ControlSlot, ...]:
    """校验一组候选 ControlSlot 字符串；返回 enum 实例元组。

    非列表/元组或包含未知值 → ``ValueError``。
    """
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"slot list must be list/tuple, got {type(values).__name__}")
    return tuple(parse_slot(v) for v in values)


__all__ = [
    "SLOT_PHASE_OWNER",
    "ControlSlot",
    "all_slot_values",
    "as_phase_label",
    "is_cross_cutting",
    "parse_slot",
    "phase_owner",
    "validate_slot_iterable",
]
