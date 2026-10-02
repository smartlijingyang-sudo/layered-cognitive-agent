"""Activated-skills section and skill-duty section (ADR-0262 C1).

``SkillDutySection`` is the run-level skill-retrieval obligation block,
mirroring the memory ``_RETRIEVAL_DUTY`` block (ADR-0260): search-before-act
(C1), no-search-no-denial discipline (C2), and the fail-closed
candidate-only settling gate (C3). Decision record (2026-10-02, 李超授权裁决):
the obligation block stays an independent section, not merged into the tools
segment, so the duty is not diluted by capability descriptions.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.cognition.brain.sections.types import block, render_activated_skills
from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra.infra import Tool

_SKILL_DUTY = (
    "## 技能检索义务（先查后动手）\n"
    "- 进入需要某产品/服务能力的具体任务前，必须先调 search_skill；"
    "检索到 → 读 SKILL.md/激活指南照做，不许绕开 skill 自造轮子。\n"
    "- 无命中 → 先用可用工具自建解决当下任务；可复用的流程应产出 "
    "skill candidate（candidate 是只读草稿，批准前不进 store）。\n"
    "- 否定纪律: 回复\"做不到/没接通/没有这个 skill\"前，必须有 "
    "search_skill 检索记录；无检索记录的否定 = 幻觉。\n"
    "- 检索失败 ≠ 检索无结果: 市场鉴权失败/网络不可用时，只许说"
    "\"检索不可用，无法确认\"，不许说\"没有这个 skill\"。\n"
    "- 易变事实复验: skill 能力声明（上下架/安装状态）是易变事实，"
    "行动前以 SkillCatalogSensor 的 manifest 投影复验，不凭记忆断言。\n"
)


class ActivatedSkillsSection:
    name: ClassVar[str] = "activated_skills"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        task: str,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        del role_profile, task, awareness, manifest, tools
        return SectionOutput(
            text=block("activated_skills", render_activated_skills(activated_skills))
        )


class SkillDutySection:
    """Model-visible mandatory skill-retrieval obligation (ADR-0262 C1)."""

    name: ClassVar[str] = "skill_duty"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        task: str,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        del role_profile, task, awareness, manifest, tools, activated_skills
        return SectionOutput(text=_SKILL_DUTY)


def build_activated_skills(config: BaseModel) -> ActivatedSkillsSection:
    del config
    return ActivatedSkillsSection()


def build_skill_duty(config: BaseModel) -> SkillDutySection:
    del config
    return SkillDutySection()


__all__ = [
    "ActivatedSkillsSection",
    "SkillDutySection",
    "build_activated_skills",
    "build_skill_duty",
]
