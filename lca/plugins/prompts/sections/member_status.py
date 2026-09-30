"""Member-status board section."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.cognition.brain.sections.types import label_line
from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra.infra import Tool


class MemberStatusSection:
    name: ClassVar[str] = "member_status_text"

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
        if awareness is None or awareness.consult_duty is None:
            return SectionOutput(text="(无状态板)")
        return SectionOutput(
            text=label_line("MEMBER_STATUS", awareness.consult_duty.member_status.as_prompt_text())
        )


def build_member_status(config: BaseModel) -> MemberStatusSection:
    del config
    return MemberStatusSection()


__all__ = ["MemberStatusSection", "build_member_status"]
