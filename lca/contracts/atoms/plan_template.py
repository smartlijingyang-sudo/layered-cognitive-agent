"""PlanTemplate 12 标准模板（ADR-0069 §五 + tracker §16.2 + PR-12 V12）。

12 PlanTemplate 实例（ADR-0069 §五）：

| ID | 名称 | 关键 relations |
|---|---|---|
| ``rag`` | Retrieval-Augmented Generation | contributes_to / reads_fact |
| ``prompt_chain`` | Sequential prompt chain | governs / evaluates |
| ``routing`` | Intent-based routing | delegates / contributes_to |
| ``parallel`` | Parallel fan-out + join | executes / delegates |
| ``orchestrator_workers`` | Orchestrator + workers | delegates / executes |
| ``evaluator_optimizer`` | Evaluator + optimizer loop | evaluates / revises |
| ``tool_using_loop`` | Tool-using loop | governs / executes |
| ``hitl`` | Human-in-the-loop | evaluates (acts as authority gate) |
| ``team`` | Multi-agent team | delegates / projects |
| ``scheduled`` | Scheduled agent | governs / executes |
| ``realtime`` | Realtime streaming agent | executes / projects |
| ``self_evolving`` | Self-evolving agent | revises / evaluates |

PlanTemplate 是 frozen dataclass：

- ``template_id`` — 唯一标识（与 ``Relation.PlanTemplate_id`` 字符串对齐）
- ``name`` — 人类可读名
- ``description`` — 一行用途
- ``relations`` — 涉及的关系集合（PR-2.5 11 关系代数子集）
- ``control_slots`` — 涉及的 ControlSlot 集合（PR-1 11 槽位）
- ``required_groups`` — FunctionalGroup 集合（PR-2 13 群分类）
- ``scope`` — 默认 ScopePlan 适用 scope
- ``version`` — schema 版本

ADR-0015 contracts 纯类型契约：PlanTemplate 不放方法，访问器 module-level
functions（``plan_template_to_dict`` / ``parse_plan_template_id``）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.relation import Relation
from lca.contracts.atoms.scope import Scope


class PlanTemplateId(str, Enum):
    """12 标准 PlanTemplate ID（ADR-0069 §五 + tracker §16.2）。"""

    RAG = "rag"
    PROMPT_CHAIN = "prompt_chain"
    ROUTING = "routing"
    PARALLEL = "parallel"
    ORCHESTRATOR_WORKERS = "orchestrator_workers"
    EVALUATOR_OPTIMIZER = "evaluator_optimizer"
    TOOL_USING_LOOP = "tool_using_loop"
    HITL = "hitl"
    TEAM = "team"
    SCHEDULED = "scheduled"
    REALTIME = "realtime"
    SELF_EVOLVING = "self_evolving"


@dataclass(frozen=True, slots=True)
class PlanTemplate:
    """PlanTemplate 不可变契约（PR-12 V12 acceptance）。"""

    template_id: str
    name: str
    description: str
    relations: tuple[Relation, ...]
    control_slots: tuple[ControlSlot, ...]
    required_groups: tuple[FunctionalGroup, ...]
    scope: Scope
    version: int = 1

    def __post_init__(self) -> None:
        if not self.template_id:
            raise ValueError("PlanTemplate.template_id must be non-empty")
        if not self.name:
            raise ValueError("PlanTemplate.name must be non-empty")
        # relations / control_slots / required_groups already tuples
        if not isinstance(self.relations, tuple):
            object.__setattr__(self, "relations", tuple(self.relations))
        if not isinstance(self.control_slots, tuple):
            object.__setattr__(self, "control_slots", tuple(self.control_slots))
        if not isinstance(self.required_groups, tuple):
            object.__setattr__(self, "required_groups", tuple(self.required_groups))
        if not isinstance(self.scope, Scope):
            object.__setattr__(self, "scope", Scope(self.scope))


# ── Module-level accessors / factories (ADR-0015) ───────────────────


def parse_plan_template_id(value: object) -> PlanTemplateId:
    """字符串 → PlanTemplateId。"""
    if isinstance(value, PlanTemplateId):
        return value
    if isinstance(value, str):
        try:
            return PlanTemplateId(value)
        except ValueError as exc:
            raise ValueError(
                f"unknown plan template id {value!r}; valid: {[t.value for t in PlanTemplateId]}"
            ) from exc
    raise TypeError(f"plan template id must be str or PlanTemplateId, got {type(value).__name__}")


def all_plan_template_ids() -> tuple[PlanTemplateId, ...]:
    """全部 12 个 PlanTemplate ID。"""
    return tuple(PlanTemplateId)


def plan_template_to_dict(template: PlanTemplate) -> dict[str, Any]:
    """JSON 友好字典（V12 acceptance §4.6）。"""
    return {
        "template_id": template.template_id,
        "name": template.name,
        "description": template.description,
        "relations": [r.value for r in template.relations],
        "control_slots": [s.value for s in template.control_slots],
        "required_groups": [g.value for g in template.required_groups],
        "scope": template.scope.value,
        "version": template.version,
    }


# ── 12 PlanTemplate 实例（PR-12 标准集）──────────────────────────


def _12_standard_templates() -> tuple[PlanTemplate, ...]:
    """12 标准 PlanTemplate 实例（PR-12 V12 acceptance）。"""
    return (
        PlanTemplate(
            template_id=PlanTemplateId.RAG.value,
            name="Retrieval-Augmented Generation",
            description="RAG: retrieve relevant context → augment prompt → generate",
            relations=(
                Relation.READS_FACT,
                Relation.CONTRIBUTES_TO,
                Relation.EMITS_FACT,
            ),
            control_slots=(
                ControlSlot.PERCEIVE_CONTEXT,
                ControlSlot.THINK_GUARD,
            ),
            required_groups=(
                FunctionalGroup.G4_PERCEPTION,
                FunctionalGroup.G5_COGNITION,
                FunctionalGroup.G6_DECISION,
            ),
            scope=Scope.RUN,
        ),
        PlanTemplate(
            template_id=PlanTemplateId.PROMPT_CHAIN.value,
            name="Sequential Prompt Chain",
            description="Chain of prompts: each prompt's output feeds next",
            relations=(
                Relation.GOVERNS,
                Relation.EVALUATES,
                Relation.CONTRIBUTES_TO,
            ),
            control_slots=(
                ControlSlot.THINK_GUARD,
                ControlSlot.STOP_DECIDE,
            ),
            required_groups=(
                FunctionalGroup.G5_COGNITION,
                FunctionalGroup.G6_DECISION,
            ),
            scope=Scope.RUN,
        ),
        PlanTemplate(
            template_id=PlanTemplateId.ROUTING.value,
            name="Intent-based Routing",
            description="Classify intent → delegate to specialized agent",
            relations=(
                Relation.CONTRIBUTES_TO,
                Relation.DELEGATES,
                Relation.READS_FACT,
            ),
            control_slots=(
                ControlSlot.PERCEIVE_CONTEXT,
                ControlSlot.ACT_AUTHORIZE,
            ),
            required_groups=(
                FunctionalGroup.G4_PERCEPTION,
                FunctionalGroup.G6_DECISION,
            ),
            scope=Scope.TURN,
        ),
        PlanTemplate(
            template_id=PlanTemplateId.PARALLEL.value,
            name="Parallel Fan-out + Join",
            description="Execute multiple branches in parallel; join results",
            relations=(
                Relation.EXECUTES,
                Relation.DELEGATES,
                Relation.PROJECTS,
            ),
            control_slots=(
                ControlSlot.ACT_EXECUTE,
                ControlSlot.ACT_SAFE_BOUNDARY,
            ),
            required_groups=(
                FunctionalGroup.G7_EXECUTION,
                FunctionalGroup.G8_COLLAB,
            ),
            scope=Scope.RUN,
        ),
        PlanTemplate(
            template_id=PlanTemplateId.ORCHESTRATOR_WORKERS.value,
            name="Orchestrator + Workers",
            description="Orchestrator dispatches tasks to worker agents",
            relations=(
                Relation.DELEGATES,
                Relation.EXECUTES,
                Relation.GOVERNS,
            ),
            control_slots=(
                ControlSlot.ACT_AUTHORIZE,
                ControlSlot.ACT_BUDGET,
            ),
            required_groups=(
                FunctionalGroup.G6_DECISION,
                FunctionalGroup.G8_COLLAB,
            ),
            scope=Scope.RUN,
        ),
        PlanTemplate(
            template_id=PlanTemplateId.EVALUATOR_OPTIMIZER.value,
            name="Evaluator + Optimizer Loop",
            description="Generate → evaluate → refine; iterate until quality threshold",
            relations=(
                Relation.EVALUATES,
                Relation.REVISES,
                Relation.GOVERNS,
            ),
            control_slots=(
                ControlSlot.THINK_GUARD,
                ControlSlot.STOP_DECIDE,
            ),
            required_groups=(
                FunctionalGroup.G5_COGNITION,
                FunctionalGroup.G11_CREATION,
            ),
            scope=Scope.RUN,
        ),
        PlanTemplate(
            template_id=PlanTemplateId.TOOL_USING_LOOP.value,
            name="Tool-Using Loop",
            description="Decide tool use → execute tool → observe → repeat",
            relations=(
                Relation.GOVERNS,
                Relation.EXECUTES,
                Relation.READS_FACT,
                Relation.EMITS_FACT,
            ),
            control_slots=(
                ControlSlot.ACT_AUTHORIZE,
                ControlSlot.ACT_BUDGET,
                ControlSlot.ACT_CONSTRAIN,
                ControlSlot.ACT_EXECUTE,
            ),
            required_groups=(
                FunctionalGroup.G6_DECISION,
                FunctionalGroup.G7_EXECUTION,
            ),
            scope=Scope.TURN,
        ),
        PlanTemplate(
            template_id=PlanTemplateId.HITL.value,
            name="Human-in-the-Loop",
            description="Pause for human approval at key decision points",
            relations=(
                Relation.EVALUATES,
                Relation.GOVERNS,
                Relation.READS_FACT,
            ),
            control_slots=(
                ControlSlot.ACT_AUTHORIZE,
                ControlSlot.THINK_GUARD,
            ),
            required_groups=(
                FunctionalGroup.G5_COGNITION,
                FunctionalGroup.G6_DECISION,
            ),
            scope=Scope.TURN,
        ),
        PlanTemplate(
            template_id=PlanTemplateId.TEAM.value,
            name="Multi-Agent Team",
            description="Multiple agents collaborate via shared blackboard / transport",
            relations=(
                Relation.DELEGATES,
                Relation.PROJECTS,
                Relation.EXECUTES,
                Relation.EMITS_FACT,
            ),
            control_slots=(
                ControlSlot.ACT_AUTHORIZE,
                ControlSlot.ACT_BUDGET,
                ControlSlot.ACT_CONSTRAIN,
                ControlSlot.ACT_EXECUTE,
            ),
            required_groups=(
                FunctionalGroup.G7_EXECUTION,
                FunctionalGroup.G8_COLLAB,
                FunctionalGroup.G12_EVIDENCE,
            ),
            scope=Scope.RUN,
        ),
        PlanTemplate(
            template_id=PlanTemplateId.SCHEDULED.value,
            name="Scheduled Agent",
            description="Run agent on cron / schedule; batch process",
            relations=(
                Relation.GOVERNS,
                Relation.EXECUTES,
                Relation.EMITS_FACT,
            ),
            control_slots=(
                ControlSlot.PERCEIVE_CONTEXT,
                ControlSlot.STOP_DECIDE,
            ),
            required_groups=(
                FunctionalGroup.G3_FACTS,
                FunctionalGroup.G7_EXECUTION,
            ),
            scope=Scope.EXPERIMENT,
        ),
        PlanTemplate(
            template_id=PlanTemplateId.REALTIME.value,
            name="Realtime Streaming Agent",
            description="Stream events with low latency; partial results projected to user",
            relations=(
                Relation.EXECUTES,
                Relation.PROJECTS,
                Relation.EMITS_FACT,
            ),
            control_slots=(
                ControlSlot.ACT_EXECUTE,
                ControlSlot.ACT_SAFE_BOUNDARY,
            ),
            required_groups=(
                FunctionalGroup.G7_EXECUTION,
                FunctionalGroup.G9_INTERACTION,
                FunctionalGroup.G12_EVIDENCE,
            ),
            scope=Scope.TURN,
        ),
        PlanTemplate(
            template_id=PlanTemplateId.SELF_EVOLVING.value,
            name="Self-Evolving Agent",
            description="Reflect on past runs; revise templates / prompts / plans",
            relations=(
                Relation.EVALUATES,
                Relation.REVISES,
                Relation.GOVERNS,
                Relation.READS_FACT,
            ),
            control_slots=(
                ControlSlot.THINK_GUARD,
                ControlSlot.STOP_DECIDE,
                ControlSlot.REMEMBER_ADMIT,
            ),
            required_groups=(
                FunctionalGroup.G11_CREATION,
                FunctionalGroup.G12_EVIDENCE,
            ),
            scope=Scope.AGENT,
        ),
    )


def standard_plan_templates() -> tuple[PlanTemplate, ...]:
    """12 个标准 PlanTemplate 实例（PR-12 V12 acceptance §4.6）。"""
    return _12_standard_templates()


__all__ = [
    "PlanTemplate",
    "PlanTemplateId",
    "all_plan_template_ids",
    "parse_plan_template_id",
    "plan_template_to_dict",
    "standard_plan_templates",
]
