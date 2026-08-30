"""LogicAddress 6 维契约（ADR-0069 §二 + tracker §15）。

6 维 LogicAddress = FunctionalGroup × ControlSlot × Scope × Authority
× Evidence × Revision。每个 production plugin 必须能完整表达 6 维
地址；缺失维度 → 警告而非错误（PR-2 阶段为软约束）。

完整度评分见 tracker §15.3：4 维评分各 25 分：

1. FunctionalGroup 命中已知群（v3 9 群 ∪ 0069 13 群）
2. ControlSlot 命中已知槽（ADR-0066 §二 11 槽）
3. Scope 在合法 ScopeGraph（8 项）
4. Evidence descriptor 已登记（journal catalog）

总分 ≥ 75 warning "LogicAddress 良好"；50-74 warning "部分完整"；
< 50 warning "缺失严重"。**不阻断 PR 合并**；``lca plugin check
--strict`` 才报错退出码 1。

ADR-0015 contracts 纯类型契约：``LogicAddress`` / ``LogicAddressScore``
是 frozen dataclass，**不放方法**。所有派生值通过 module-level 函数访问。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot, parse_slot
from lca.contracts.atoms.functional_group import FunctionalGroup, parse_functional_group
from lca.contracts.atoms.scope import Scope, canonical_scope, parse_scope


@dataclass(frozen=True, slots=True)
class LogicAddress:
    """6 维 LogicAddress（ADR-0069 §二）。

    全部字段 optional；缺失维度仍可构造实例。``None`` 表示"未声明"——
    不等价于空集。

    派生属性见 module-level 函数：

    - ``is_complete_address(addr)`` — 6 维是否全部声明
    - ``declared_dim_count(addr)`` — 已声明维度数（0..6）
    - ``canonical_scope_of(addr)`` — scope 沿 SCOPE_ALIAS 折叠
    - ``logic_address_to_dict(addr)`` — JSON 友好字典
    """

    functional_group: FunctionalGroup | None = None
    control_slot: ControlSlot | None = None
    scope: Scope | None = None
    authority: tuple[str, ...] = ()  # capability grant / read / write / effect
    evidence: tuple[str, ...] = ()  # Journal catalog EventDescriptor names
    revision: str | None = None  # plan / artifact / release version 标签

    def __post_init__(self) -> None:
        # Type narrowing: control_slot / functional_group / scope 通过 parser
        # 容错（None 仍合法）
        if self.functional_group is not None and not isinstance(
            self.functional_group, FunctionalGroup
        ):
            object.__setattr__(
                self, "functional_group", parse_functional_group(self.functional_group)
            )
        if self.control_slot is not None and not isinstance(self.control_slot, ControlSlot):
            object.__setattr__(self, "control_slot", parse_slot(self.control_slot))
        if self.scope is not None and not isinstance(self.scope, Scope):
            object.__setattr__(self, "scope", parse_scope(self.scope))
        # authority / evidence must be tuple[str, ...]
        if not isinstance(self.authority, tuple):
            object.__setattr__(self, "authority", tuple(self.authority))
        if not isinstance(self.evidence, tuple):
            object.__setattr__(self, "evidence", tuple(self.evidence))
        if self.revision is not None and not isinstance(self.revision, str):
            object.__setattr__(self, "revision", str(self.revision))
        if self.revision == "":
            # empty string is degenerate → normalize to None
            object.__setattr__(self, "revision", None)


# ── Module-level accessors (ADR-0015 contracts purity) ──────────────


def is_complete_address(address: LogicAddress) -> bool:
    """是否声明了 6 维全部字段（authority / evidence 可以是空 tuple）。"""
    return (
        address.functional_group is not None
        and address.control_slot is not None
        and address.scope is not None
        and address.revision is not None
    )


def declared_dim_count(address: LogicAddress) -> int:
    """声明维度数（0..6；authority / evidence 算作声明 = 即使空 tuple）。"""
    count = 2  # authority + evidence always present (default [])
    if address.functional_group is not None:
        count += 1
    if address.control_slot is not None:
        count += 1
    if address.scope is not None:
        count += 1
    if address.revision is not None:
        count += 1
    return count


def canonical_scope_of(address: LogicAddress) -> Scope | None:
    """返回 scope 的规范形式（沿 SCOPE_ALIAS 折叠）。"""
    if address.scope is None:
        return None
    return canonical_scope(address.scope)


def logic_address_to_dict(address: LogicAddress) -> dict[str, Any]:
    """JSON 友好字典。"""
    canonical = canonical_scope_of(address)
    return {
        "functional_group": (
            address.functional_group.value if address.functional_group is not None else None
        ),
        "control_slot": (address.control_slot.value if address.control_slot is not None else None),
        "scope": address.scope.value if address.scope is not None else None,
        "scope_canonical": canonical.value if canonical is not None else None,
        "authority": list(address.authority),
        "evidence": list(address.evidence),
        "revision": address.revision,
    }


# ── LogicAddressScore ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LogicAddressScore:
    """LogicAddress 评分结果（tracker §15.3 V9 评分定义）。

    4 维 × 25 分 = 100 分满分。``total`` 触发 warning 等级。
    """

    functional_group_hit: bool
    control_slot_hit: bool
    scope_hit: bool
    evidence_hit: bool
    total: int


def score_level(score: LogicAddressScore) -> str:
    """warning 等级（tracker §15.3）；module-level function（ADR-0015）。"""
    if score.total >= 75:
        return "good"
    if score.total >= 50:
        return "partial"
    return "missing"


def score_logic_address(address: LogicAddress) -> LogicAddressScore:
    """评分 LogicAddress（tracker §15.3 V9 评分）。

    评分条件：

    - functional_group_hit: ``address.functional_group`` ∈ {v3 9 群 ∪ ADR-0069 13 群}
      简化为：``functional_group`` 不为 None 即得分（FunctionalGroup 枚举
      已包含 13 群全集——v3 9 群 ↔ 13 群映射由 V3_TO_0069_MAPPING 显式
      提供；plugin 作者直接填 13 群 enum 值即可）
    - control_slot_hit: ``address.control_slot`` ∈ ADR-0066 §二 11 槽
    - scope_hit: ``address.scope`` ∈ ADR-0074 §三 7~8 scope
    - evidence_hit: ``address.evidence`` 至少 1 个 descriptor 名
    """
    fg_hit = address.functional_group is not None
    cs_hit = address.control_slot is not None
    sc_hit = address.scope is not None
    ev_hit = bool(address.evidence) and all(isinstance(e, str) and e for e in address.evidence)
    total = (
        (25 if fg_hit else 0)
        + (25 if cs_hit else 0)
        + (25 if sc_hit else 0)
        + (25 if ev_hit else 0)
    )
    return LogicAddressScore(
        functional_group_hit=fg_hit,
        control_slot_hit=cs_hit,
        scope_hit=sc_hit,
        evidence_hit=ev_hit,
        total=total,
    )


__all__ = [
    "LogicAddress",
    "LogicAddressScore",
    "canonical_scope_of",
    "declared_dim_count",
    "is_complete_address",
    "logic_address_to_dict",
    "score_level",
    "score_logic_address",
]
