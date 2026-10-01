"""Role / goal / backstory sections — the assistant's identity card."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.cognition.brain.sections.types import label_line
from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.protocols.runtime.infra.infra import Tool
from lca.plugins.prompts.sections.base import _PERSONA_INJECTION_WARNING


class RoleSection:
    name: ClassVar[str] = "role"

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        return SectionOutput(text=label_line("ROLE", role_profile.role))


class GoalSection:
    name: ClassVar[str] = "goal"

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        return SectionOutput(text=label_line("GOAL", role_profile.goal))


class BackstorySection:
    name: ClassVar[str] = "backstory"

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        # The warning names SOUL.md. Emit it only after a real standing
        # backstory, so an unbound session cannot go looking for a file
        # that was never loaded.
        text = (role_profile.backstory or "").strip()
        if not text:
            return SectionOutput(text="")
        return SectionOutput(
            text=label_line("BACKSTORY", text) + "\n\n" + _PERSONA_INJECTION_WARNING
        )


def build_role_section(config: BaseModel) -> RoleSection:
    del config
    return RoleSection()


def build_goal_section(config: BaseModel) -> GoalSection:
    del config
    return GoalSection()


def build_backstory_section(config: BaseModel) -> BackstorySection:
    del config
    return BackstorySection()


__all__ = [
    "BackstorySection",
    "GoalSection",
    "RoleSection",
    "build_backstory_section",
    "build_goal_section",
    "build_role_section",
]
