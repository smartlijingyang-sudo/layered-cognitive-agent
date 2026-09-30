"""Activated-skills section."""

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


def build_activated_skills(config: BaseModel) -> ActivatedSkillsSection:
    del config
    return ActivatedSkillsSection()


__all__ = ["ActivatedSkillsSection", "build_activated_skills"]
