"""11 关系代数（ADR-0069 §三）。

11 种关系是 plugin / artifact / capability / fact 之间允许的全部
关系类型。新增第 12 关系必须 ADR 批准（C6 改闭集）。

11 关系分类：

**5 老关系**（ADR-0061 已支持 capabilities DAG）：

- ``provides`` — 提供 capability / 接口（registry owner）
- ``requires`` — 依赖 capability / 接口（registry consumer）
- ``contributes_to`` — 向群服务投稿（ADR-0056）
- ``reads_fact`` — 读取 Journal fact descriptor
- ``emits_fact`` — 发射 Journal fact descriptor

**6 新关系**（PR-2.5 落地）：

- ``governs`` — 以治理身份覆盖 / 决定 / narrow（think.guard / act.authorize 槽位）
- ``executes`` — 执行 / dispatch effect（act.execute / act.safe-boundary 槽位）
- ``delegates`` — 委派（team member → member、lead → member、agent → sub-agent）
- ``projects`` — 投影到 view / 视图（observability / journal projector）
- ``revises`` — 修订（artifact state transition / plan revision）
- ``evaluates`` — 评估 / 评分（scoring / verifier / property test）

全局不变量（ADR-0069 §三）：

1. authority 仅可向子 scope 衰减（capability grant ⊆ 父代理）
2. world effect 仅可经 G7 的 CommandEnvelope 穿出
3. facts 仅可追加，state 仅可由 Reducer 投影
4. profile / artifact 的变更只能形成 immutable PlanRevision
5. projection 不得回写 facts 或 business state
6. plugin 不得通过 live Context / global helper 绕开这些关系
"""

from __future__ import annotations

from enum import Enum


class Relation(str, Enum):
    """11 关系代数闭集（ADR-0069 §三）。

    字符串值稳定（序列化 / journal / plan_ref 引用）；新增关系必须
    经 ADR 批准，**禁止运行时动态发明**。
    """

    PROVIDES = "provides"
    REQUIRES = "requires"
    CONTRIBUTES_TO = "contributes_to"
    READS_FACT = "reads_fact"
    EMITS_FACT = "emits_fact"
    GOVERNS = "governs"
    EXECUTES = "executes"
    DELEGATES = "delegates"
    PROJECTS = "projects"
    REVISES = "revises"
    EVALUATES = "evaluates"


# ── 关系分类表 ──────────────────────────────────────────


# 5 老关系（ADR-0061 capabilities DAG 已支持）
_LEGACY_RELATIONS: frozenset[Relation] = frozenset(
    {
        Relation.PROVIDES,
        Relation.REQUIRES,
        Relation.CONTRIBUTES_TO,
        Relation.READS_FACT,
        Relation.EMITS_FACT,
    }
)

# 6 新关系（PR-2.5 落地）
NEW_RELATIONS: frozenset[Relation] = frozenset(
    {
        Relation.GOVERNS,
        Relation.EXECUTES,
        Relation.DELEGATES,
        Relation.PROJECTS,
        Relation.REVISES,
        Relation.EVALUATES,
    }
)


# 关系 → 默认出现的群 / 阶段提示（PR-12 图谱可视化用）
RELATION_GROUP_HINT: dict[Relation, str] = {
    Relation.PROVIDES: "G10",
    Relation.REQUIRES: "G10",
    Relation.CONTRIBUTES_TO: "G10",
    Relation.READS_FACT: "G12",
    Relation.EMITS_FACT: "G12",
    Relation.GOVERNS: "G6",
    Relation.EXECUTES: "G7",
    Relation.DELEGATES: "G8",
    Relation.PROJECTS: "G9",
    Relation.REVISES: "G11",
    Relation.EVALUATES: "G12",
}
"""关系 → ADR-0069 13 群提示（PR-12 图谱可视化颜色用；非强制）"""


def parse_relation(value: object) -> Relation:
    """字符串 / 枚举 → Relation。值未匹配 → ``ValueError``。"""
    if isinstance(value, Relation):
        return value
    if isinstance(value, str):
        try:
            return Relation(value)
        except ValueError as exc:
            raise ValueError(
                f"unknown relation {value!r}; valid: {[r.value for r in Relation]}"
            ) from exc
    raise TypeError(f"relation must be str or Relation, got {type(value).__name__}")


def validate_relations(values: object) -> tuple[Relation, ...]:
    """校验一组候选 Relation 字符串；返回 enum 实例元组。

    非 list/tuple 或包含未知值 → ``ValueError``。
    """
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"relation list must be list/tuple, got {type(values).__name__}")
    return tuple(parse_relation(v) for v in values)


def all_relation_values() -> tuple[str, ...]:
    """全部关系字符串值（顺序确定）。"""
    return tuple(r.value for r in Relation)


__all__ = [
    "NEW_RELATIONS",
    "RELATION_GROUP_HINT",
    "Relation",
    "all_relation_values",
    "parse_relation",
    "validate_relations",
]
