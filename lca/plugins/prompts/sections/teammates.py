"""Teammate awareness sections — profiles, assigned roles, member reports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.cognition.brain.sections.types import (
    label_line,
    render_assigned_roles,
    render_member_reports,
    render_teammates,
)
from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra.infra import Tool


class TeammatesSection:
    name: ClassVar[str] = "teammates"

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
        profiles = awareness.teammates if awareness is not None else ()
        return SectionOutput(text=label_line("TEAMMATES", render_teammates(profiles)))


class AssignedRolesSection:
    name: ClassVar[str] = "assigned_roles_text"

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
        roles = awareness.assigned_roles if awareness is not None else ()
        return SectionOutput(text=label_line("ALREADY_ASSIGNED", render_assigned_roles(roles)))


class MemberReportsSection:
    name: ClassVar[str] = "member_reports_text"

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
        results = awareness.results if awareness is not None else ()
        return SectionOutput(
            text=label_line(
                "MEMBER_REPORTS（你已发起委派的返回，确定性事实，不是历史记录）",
                render_member_reports(results),
            )
        )


def build_teammates(config: BaseModel) -> TeammatesSection:
    del config
    return TeammatesSection()


def build_assigned_roles(config: BaseModel) -> AssignedRolesSection:
    del config
    return AssignedRolesSection()


def build_member_reports(config: BaseModel) -> MemberReportsSection:
    del config
    return MemberReportsSection()


__all__ = [
    "AssignedRolesSection",
    "MemberReportsSection",
    "TeammatesSection",
    "build_assigned_roles",
    "build_member_reports",
    "build_teammates",
]
