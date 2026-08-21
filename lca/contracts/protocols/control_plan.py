"""ControlPlan 数据面契约（ADR-0066 §三 / ADR-0074 PR-1）。

ControlPlan 是已解析 profile 在控制面单一不可变投影：

- 每条 ControlEntry 描述一个插件对某个 Control Slot 的贡献
- Activation 是小型、总是可判定的数据 DSL（ADR-0066 §三：只允许对
  已登记事实做布尔组合、等值、集合、数值比较和存在性判断；不得读
  环境变量、执行表达式、调用网络或反射对象）
- Aggregation / FailureMode 由槽位默认提供（ADR-0066 §四）
- ``plan_hash`` 是 ControlPlan 的稳定摘要，用于 plan_ref 绑定（PR-3 / PR-6）

不变量：

- ControlPlan 是 frozen dataclass；任何 mutate 必须产生新对象
- ControlEntry 不可跨 ControlPlan 共享
- Activation 默认 ``ALWAYS``（永真），不是 None——避免 None 检查
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot, parse_slot

# ── Aggregation / FailureMode enums ─────────────────────────────


class AggregationMode(str, Enum):
    """同槽位 verdict 聚合器（ADR-0066 §四）。

    - ``DENY_ON_ANY_DENY`` — 任一拒绝即不进入执行窄门（authorize / constrain）
    - ``DENY_ON_EXHAUSTED`` — 不足时拒绝或产生已定义的降级请求（budget）
    - ``STOP_ON_ANY_STOP`` — 任一硬终止条件结束循环（stop）
    - ``DECISION_PRIORITY`` — 严格优先级 ``stop > ask_human > rewrite > allow``
    - ``NO_AGGREGATE`` — 不聚合业务控制（observe / safe-boundary）
    """

    DENY_ON_ANY_DENY = "deny_on_any_deny"
    DENY_ON_EXHAUSTED = "deny_on_exhausted"
    STOP_ON_ANY_STOP = "stop_on_any_stop"
    DECISION_PRIORITY = "decision_priority"
    NO_AGGREGATE = "no_aggregate"


class FailureMode(str, Enum):
    """同槽位插件失败治理（ADR-0066 §三 failure_mode 字段）。

    - ``DENY`` — 失败 = 拒绝（fail-closed；authorize / budget 默认）
    - ``STOP`` — 失败 = 触发 stop（stop 默认）
    - ``DEGRADE`` — 失败 = 降级（受控降级，需保留 degraded_from）
    - ``IGNORE`` — 失败 = 忽略（仅观察口允许；observe）
    """

    DENY = "deny"
    STOP = "stop"
    DEGRADE = "degrade"
    IGNORE = "ignore"


# Default aggregator/failure per slot — ADR-0066 §四 单调聚合表
SLOT_DEFAULT_AGGREGATION: dict[ControlSlot, AggregationMode] = {
    ControlSlot.PERCEIVE_CONTEXT: AggregationMode.NO_AGGREGATE,
    ControlSlot.THINK_GUARD: AggregationMode.DECISION_PRIORITY,
    ControlSlot.ACT_AUTHORIZE: AggregationMode.DENY_ON_ANY_DENY,
    ControlSlot.ACT_BUDGET: AggregationMode.DENY_ON_EXHAUSTED,
    ControlSlot.ACT_CONSTRAIN: AggregationMode.DENY_ON_ANY_DENY,
    ControlSlot.ACT_EXECUTE: AggregationMode.NO_AGGREGATE,
    ControlSlot.ACT_SAFE_BOUNDARY: AggregationMode.NO_AGGREGATE,
    ControlSlot.REMEMBER_ADMIT: AggregationMode.NO_AGGREGATE,
    ControlSlot.STOP_DECIDE: AggregationMode.STOP_ON_ANY_STOP,
    ControlSlot.OBSERVE_CHECKPOINT: AggregationMode.NO_AGGREGATE,
    ControlSlot.OBSERVE_WILDCARD: AggregationMode.NO_AGGREGATE,
}

SLOT_DEFAULT_FAILURE: dict[ControlSlot, FailureMode] = {
    ControlSlot.PERCEIVE_CONTEXT: FailureMode.IGNORE,
    ControlSlot.THINK_GUARD: FailureMode.DENY,
    ControlSlot.ACT_AUTHORIZE: FailureMode.DENY,
    ControlSlot.ACT_BUDGET: FailureMode.DENY,
    ControlSlot.ACT_CONSTRAIN: FailureMode.DENY,
    ControlSlot.ACT_EXECUTE: FailureMode.STOP,
    ControlSlot.ACT_SAFE_BOUNDARY: FailureMode.STOP,
    ControlSlot.REMEMBER_ADMIT: FailureMode.IGNORE,
    ControlSlot.STOP_DECIDE: FailureMode.STOP,
    ControlSlot.OBSERVE_CHECKPOINT: FailureMode.IGNORE,
    ControlSlot.OBSERVE_WILDCARD: FailureMode.IGNORE,
}


# ── Activation DSL ────────────────────────────────────────────────


# Operator set: ADR-0066 §三 允许的最小 boolean DSL（always-deterministic）
ALLOWED_OPERATORS: frozenset[str] = frozenset(
    {
        "always",
        "all",
        "any",
        "not",
        "in",
        "not_in",
        "eq",
        "ne",
        "lt",
        "le",
        "gt",
        "ge",
        "exists",
        "missing",
    }
)
"""Activation DSL 允许的操作符集；Resolve / lint 必须拒绝集合外操作符。"""


@dataclass(frozen=True, slots=True)
class Activation:
    """小型、总是可判定的数据 DSL（ADR-0066 §三）。

    仅支持对已登记事实做布尔组合、等值、集合、数值比较和存在性判断。
    不得读取环境变量、执行表达式、调用网络或反射对象。

    ``predicate`` 是结构化字典，例如：

    - ``{"always": True}`` — 永真（默认）
    - ``{"all": [{"fact": "task.action_type", "in": ["USE_TOOL"]}]}``
    - ``{"any": [{"fact": "risk", "ge": 3}, {"fact": "approval_pending", "eq": True}]}``

    本 dataclass **不**求值 ``predicate``（resolver 阶段不做求值——求值
    是运行时 ActivationRegistry 的职责，PR-3 PlanCompiler 之后才需要）；
    这里只冻结结构与校验操作符集。
    """

    predicate: Mapping[str, Any] = field(default_factory=lambda: _ALWAYS_PREDICATE)

    def __post_init__(self) -> None:
        if not isinstance(self.predicate, Mapping):
            raise ValueError(
                f"Activation.predicate must be mapping, got {type(self.predicate).__name__}"
            )
        _validate_predicate(self.predicate, path="$")


_ALWAYS_PREDICATE: dict[str, Any] = {"always": True}
"""默认永真谓词；避免 None 检查分支。"""


def always() -> Activation:
    """永真 Activation（默认；不可变单例等价）。"""
    return Activation(_ALWAYS_PREDICATE)


def _validate_predicate(node: Any, *, path: str) -> None:
    """递归校验 Activation 谓词结构（操作符白名单 + 叶子形状）。

    Leaf shape per ADR-0066 §三:

        {"fact": "<descriptor>", <op>: <value>}

    where ``<op>`` is one of the leaf operators (``in``, ``eq``, ``lt`` …).
    """
    if not isinstance(node, Mapping):
        raise ValueError(f"activation node at {path} must be mapping")
    if not node:
        raise ValueError(f"activation node at {path} must not be empty")

    # 'always' is a singleton operator
    if "always" in node:
        if len(node) != 1 or node["always"] is not True:
            raise ValueError(f"activation 'always' at {path} must be {{'always': True}}")
        return

    # Composite operators: {all: [...]} / {any: [...]} / {not: {...}}
    for composite in ("all", "any"):
        if composite in node:
            if len(node) != 1:
                raise ValueError(f"activation {composite!r} at {path} must be the sole key")
            body = node[composite]
            if not isinstance(body, (list, tuple)):
                raise ValueError(f"activation {composite!r} at {path} body must be list")
            for idx, sub in enumerate(body):
                _validate_predicate(sub, path=f"{path}.{composite}[{idx}]")
            return

    if "not" in node:
        if len(node) != 1:
            raise ValueError(f"activation 'not' at {path} must be the sole key")
        body = node["not"]
        if not isinstance(body, Mapping):
            raise ValueError(f"activation 'not' at {path} body must be mapping")
        _validate_predicate(body, path=f"{path}.not")
        return

    # Leaf shape: must contain 'fact' + exactly one leaf operator
    if "fact" not in node:
        raise ValueError(
            f"activation leaf at {path} missing 'fact' key (got keys={sorted(node.keys())})"
        )
    fact = node["fact"]
    if not isinstance(fact, str) or not fact:
        raise ValueError(f"activation leaf at {path} 'fact' must be non-empty str")

    leaf_keys = {k for k in node if k != "fact"}
    unknown = leaf_keys - _LEAF_OPERATORS
    if unknown:
        raise ValueError(
            f"activation leaf at {path} has unknown operator(s) {sorted(unknown)}; "
            f"allowed: {sorted(_LEAF_OPERATORS)}"
        )
    if not leaf_keys:
        raise ValueError(f"activation leaf at {path} needs a comparison operator after 'fact'")
    if len(leaf_keys) > 1:
        raise ValueError(
            f"activation leaf at {path} has multiple operators {sorted(leaf_keys)}; "
            f"expected exactly one"
        )


_LEAF_OPERATORS: frozenset[str] = frozenset(
    {"in", "not_in", "eq", "ne", "lt", "le", "gt", "ge", "exists", "missing"}
)
"""Leaf operator set — applies to ``{fact: <descriptor>, <op>: <value>}`` nodes."""


# ── ControlEntry / ControlPlan ────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ControlEntry:
    """一个插件对一个 Control Slot 的贡献（ADR-0066 §三）。

    字段与 ADR-0066 §三字段表对齐：

    - ``plugin_id`` — 唯一 plugin id
    - ``slot`` — 槽位（必填；解析时强制 ∈ ADR-0066 §二 + tracker §19）
    - ``activation`` — 启用条件（默认 always）
    - ``order`` — 同槽位并列稳定性（升序）
    - ``aggregation`` — 覆盖槽位默认（None 时使用 SLOT_DEFAULT_AGGREGATION）
    - ``failure_mode`` — 覆盖槽位默认（None 时使用 SLOT_DEFAULT_FAILURE）
    - ``authority`` — 所需 capability grant 列表
    - ``reads`` — 事实依赖列表（descriptor 名）
    - ``emits`` — 可观测事件列表（descriptor 名）
    - ``effect_class`` — effect 边界（"none" / "tools" / "memory" / …）
    - ``source`` — bundle/patch 路径（追溯用）
    """

    plugin_id: str
    slot: ControlSlot
    activation: Activation = field(default_factory=always)
    order: int = 100
    aggregation: AggregationMode | None = None
    failure_mode: FailureMode | None = None
    authority: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    effect_class: str = "none"
    source: str = ""

    def __post_init__(self) -> None:
        if not self.plugin_id:
            raise ValueError("ControlEntry.plugin_id must be non-empty")
        if not isinstance(self.slot, ControlSlot):
            raise TypeError(
                f"ControlEntry.slot must be ControlSlot, got {type(self.slot).__name__}"
            )
        # Slot allowlist re-validation: parse_slot accepts all enum members; if
        # we ever tighten the allowed set further, surface here.
        parse_slot(self.slot.value)


@dataclass(frozen=True, slots=True)
class ControlPlan:
    """已解析 profile 在控制面的不可变投影（ADR-0066 §六 + ADR-0068 §一）。

    - ``profile_path`` — 来源 profile 路径
    - ``entries`` — 所有 ControlEntry（跨槽位，按 slot → order 排序）
    - ``by_slot`` — 槽位 → 该槽位 entry 元组（解析时建索引）
    - ``plan_hash`` — ControlPlan 稳定摘要（PR-3 / PR-6 plan_ref 绑定）
    """

    profile_path: str
    entries: tuple[ControlEntry, ...]
    by_slot: Mapping[ControlSlot, tuple[ControlEntry, ...]]
    plan_hash: str

    def __post_init__(self) -> None:
        if not self.profile_path:
            raise ValueError("ControlPlan.profile_path must be non-empty")
        if not isinstance(self.entries, tuple):
            raise ValueError("ControlPlan.entries must be tuple")
        if not isinstance(self.by_slot, Mapping):
            raise ValueError("ControlPlan.by_slot must be mapping")
        seen_plugins: set[str] = set()
        for entry in self.entries:
            if entry.plugin_id in seen_plugins:
                raise ValueError(f"ControlPlan contains duplicate plugin_id {entry.plugin_id!r}")
            seen_plugins.add(entry.plugin_id)
        # Auto-sort entries by (slot, order, plugin_id) for stable iteration.
        # We do not mutate the input tuple via __setattr__ (frozen dataclass
        # would raise) — instead, callers and constructors already pass sorted
        # tuples, and we re-validate by checking that ``self.entries`` is
        # already sorted. If not, raise — don't silently re-sort frozen fields.
        sorted_entries = tuple(
            sorted(self.entries, key=lambda e: (e.slot.value, e.order, e.plugin_id))
        )
        if sorted_entries != self.entries:
            raise ValueError(
                "ControlPlan.entries must be sorted by (slot, order, plugin_id); "
                "use compute_control_plan_hash() to derive a canonical plan."
            )
        # Cross-validate by_slot against entries.
        derived_by_slot: dict[ControlSlot, list[ControlEntry]] = {}
        for entry in self.entries:
            derived_by_slot.setdefault(entry.slot, []).append(entry)
        for slot, expected in self.by_slot.items():
            derived = tuple(derived_by_slot.get(slot, ()))
            if derived != tuple(expected):
                raise ValueError(f"ControlPlan.by_slot[{slot.value}] inconsistent with entries")


# ── Module-level accessors (ADR-0015 contracts purity: no methods on
# contracts @dataclass). Caller passes the plan explicitly. ────────────


def slot_entries(plan: ControlPlan, slot: ControlSlot | str) -> tuple[ControlEntry, ...]:
    """按 slot 查询 entry；未命中返回空元组。"""
    return plan.by_slot.get(parse_slot(slot), ())


def is_slot_empty(plan: ControlPlan, slot: ControlSlot | str) -> bool:
    """某槽位是否完全无 entry。"""
    return len(slot_entries(plan, slot)) == 0


def slots_covered(plan: ControlPlan) -> frozenset[ControlSlot]:
    """实际有 entry 的槽位集合。"""
    return frozenset(plan.by_slot.keys())


def all_slots() -> tuple[ControlSlot, ...]:
    """所有可能槽位（按枚举顺序），便于诊断报告按固定顺序遍历。"""
    return tuple(ControlSlot)


def slots_missing(plan: ControlPlan) -> tuple[ControlSlot, ...]:
    """未有任何 entry 的槽位（诊断用）。"""
    return tuple(s for s in all_slots() if is_slot_empty(plan, s))


def control_plan_to_dict(plan: ControlPlan) -> dict[str, Any]:
    """JSON 友好字典（不丢 ``effect_class`` / ``source`` 等附加字段）。"""
    return {
        "profile_path": plan.profile_path,
        "plan_hash": plan.plan_hash,
        "entries": [
            {
                "plugin_id": e.plugin_id,
                "slot": e.slot.value,
                "activation": dict(e.activation.predicate),
                "order": e.order,
                "aggregation": (e.aggregation.value if e.aggregation is not None else None),
                "failure_mode": (e.failure_mode.value if e.failure_mode is not None else None),
                "authority": list(e.authority),
                "reads": list(e.reads),
                "emits": list(e.emits),
                "effect_class": e.effect_class,
                "source": e.source,
            }
            for e in plan.entries
        ],
        "by_slot": {
            slot.value: [e.plugin_id for e in entries] for slot, entries in plan.by_slot.items()
        },
    }


def compute_control_plan_hash(
    entries: tuple[ControlEntry, ...],
    profile_path: str,
) -> str:
    """ControlPlan 的稳定摘要（PR-3 / PR-6 引用；PR-3 之前仅为诊断值）。

    同 profile + 同 entries → 同 hash；跨运行 stable。输入序列先按
    (slot, order, plugin_id) 排序再 hash，避免 dict 顺序敏感性。
    """
    sorted_entries = sorted(entries, key=lambda e: (e.slot.value, e.order, e.plugin_id))
    payload = {
        "profile_path": profile_path,
        "entries": [
            {
                "plugin_id": e.plugin_id,
                "slot": e.slot.value,
                "activation": _activation_canonical(e.activation.predicate),
                "order": e.order,
                "aggregation": (e.aggregation.value if e.aggregation is not None else None),
                "failure_mode": (e.failure_mode.value if e.failure_mode is not None else None),
                "authority": sorted(e.authority),
                "reads": sorted(e.reads),
                "emits": sorted(e.emits),
                "effect_class": e.effect_class,
            }
            for e in sorted_entries
        ],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _activation_canonical(predicate: Mapping[str, Any]) -> Any:
    """Activation 谓词的 canonical 形式（用于 hash）。"""
    if "always" in predicate:
        return {"always": True}
    if "all" in predicate:
        return {"all": [_activation_canonical(sub) for sub in predicate["all"]]}
    if "any" in predicate:
        return {"any": [_activation_canonical(sub) for sub in predicate["any"]]}
    if "not" in predicate:
        return {"not": _activation_canonical(predicate["not"])}
    # Leaf: stable order via sorted keys
    return {k: predicate[k] for k in sorted(predicate)}


__all__ = [
    "ALLOWED_OPERATORS",
    "SLOT_DEFAULT_AGGREGATION",
    "SLOT_DEFAULT_FAILURE",
    "Activation",
    "AggregationMode",
    "ControlEntry",
    "ControlPlan",
    "FailureMode",
    "all_slots",
    "always",
    "compute_control_plan_hash",
    "control_plan_to_dict",
    "is_slot_empty",
    "slot_entries",
    "slots_covered",
    "slots_missing",
]
