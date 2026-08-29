"""13 原语群分类学（ADR-0069 §一 + tracker §15.2）。

13 群是 v3 8/9 群宪法原语基础集（[v3 宪法 §3.2](../design/2026-08-19-cognitive-primitive-constitution-v3.md)）
的扩展分类学：v3 9 群 = State / Perceive / Think / Gate / Act / Memory /
Collaboration / Journal / Composition；ADR-0069 在此基础上把
"Perceive" 拆成 "Spacetime / Environment & Context" 与 "Perception &
Grounding" 两群、把 "Journal" 收进 "Facts / State / Knowledge" 一群，
并新增 "Constitution / Identity / Collaboration / Interaction /
Creation / Evidence" 等 4 群，达到 13 群。

PR-2 阶段：``functional_group`` 是 ``PluginManifest`` / ``PluginDefinition``
可选字段；``lca plugin check`` 输出该 plugin 的群归属（warning 而非
error）。**PluginManifest 可不填该字段**，不阻断 PR 合并。
"""

from __future__ import annotations

from enum import Enum


class FunctionalGroup(str, Enum):
    """13 原语群分类学（ADR-0069 §一）。

    群成员声明是 plugin 作者的"语义坐标"声明；缺失 = plugin 没有清晰
    群归属（warning，不阻断）。每个 plugin **只能有一个主群**；多主群
    = 架构违规（C1 不变量），由 ``lca plugin check --strict`` 阻断。
    """

    G0_CON_KERNEL = "G0"  # Constitution & Kernel
    G1_IDENTITY = "G1"  # Identity, Intent & Contract
    G2_SPACETIME = "G2"  # Spacetime, Environment & Context
    G3_FACTS = "G3"  # Facts, State & Knowledge
    G4_PERCEPTION = "G4"  # Perception & Grounding
    G5_COGNITION = "G5"  # Cognition, Models & Planning
    G6_DECISION = "G6"  # Decision, Command & Control
    G7_EXECUTION = "G7"  # Execution, Tools & Operations
    G8_COLLAB = "G8"  # Collaboration & Organization
    G9_INTERACTION = "G9"  # Interaction, Transport & Interop
    G10_COMPOSITION = "G10"  # Composition, Configuration & Runtime Governance
    G11_CREATION = "G11"  # Creation, Learning & Evolution
    G12_EVIDENCE = "G12"  # Evidence, Evaluation & Operations


# ── V3 9 群 → ADR-0069 13 群 映射（v3.1 §1.1 + tracker §15.2）──────

V3_TO_0069_MAPPING: dict[str, tuple[FunctionalGroup, ...]] = {
    "State": (FunctionalGroup.G3_FACTS,),
    "Perceive": (FunctionalGroup.G2_SPACETIME, FunctionalGroup.G4_PERCEPTION),
    "Think": (FunctionalGroup.G5_COGNITION,),
    "Gate": (FunctionalGroup.G6_DECISION,),
    "Act": (FunctionalGroup.G7_EXECUTION,),
    "Memory": (FunctionalGroup.G3_FACTS,),
    "Collaboration": (FunctionalGroup.G8_COLLAB,),
    "Journal": (FunctionalGroup.G3_FACTS, FunctionalGroup.G12_EVIDENCE),
    "Composition": (FunctionalGroup.G10_COMPOSITION,),
}
"""v3 宪法 9 群 → ADR-0069 13 群映射。

一个 v3 群可能映射到 1~2 个 0069 群——v3 是认知内化分类，0069 是工程
外化分类，二者非简单细分关系。
"""


def parse_functional_group(value: object) -> FunctionalGroup:
    """字符串 / 枚举 → FunctionalGroup。值未匹配 → ``ValueError``。"""
    if isinstance(value, FunctionalGroup):
        return value
    if isinstance(value, str):
        try:
            return FunctionalGroup(value)
        except ValueError as exc:
            raise ValueError(
                f"unknown functional group {value!r}; valid: {[g.value for g in FunctionalGroup]}"
            ) from exc
    raise TypeError(f"functional group must be str or FunctionalGroup, got {type(value).__name__}")


def all_group_ids() -> tuple[str, ...]:
    """全部群 id（顺序确定，便于诊断报告按固定顺序遍历）。"""
    return tuple(g.value for g in FunctionalGroup)


__all__ = [
    "V3_TO_0069_MAPPING",
    "FunctionalGroup",
    "all_group_ids",
    "parse_functional_group",
]
