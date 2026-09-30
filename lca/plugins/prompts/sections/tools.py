"""Tool catalog, sandbox workspace, and available-skills sections."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.cognition.brain.prompt.surface import PromptSurface
from lca.cognition.brain.sections.types import block
from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra.infra import Tool


class ToolsSection:
    """Renders the model's <tools> XML catalog for this turn.

    Native ``tool_calls`` schemas on the same request are the availability
    SSOT. A placeholder that says there are no tools would contradict that
    wire, so an empty catalog renders nothing; the gap is recorded on the
    observation plane via ``used_fallback``. Workspace addressing lives in
    ``CloudSandboxSection``, not here.
    """

    name: ClassVar[str] = "tools"

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
        del role_profile, task, awareness, manifest, activated_skills
        xml = PromptSurface.default().render_tools_xml(tools)
        return SectionOutput(
            text=block("tools", xml),
            used_fallback=not xml,
        )


class CloudSandboxSection:
    """Workspace root, outputs, and staged uploads for the bound plane.

    Independent of the XML tool catalog. ``render_turn`` passes ``tools=()``
    because native schemas travel on the request; this section still renders.
    """

    name: ClassVar[str] = "cloud_sandbox"

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
        del role_profile, task, awareness, manifest, activated_skills
        return SectionOutput(text=PromptSurface.default().render_sandbox_block(tools))


@dataclass
class AvailableSkillsSection:
    catalog_skills_provider: Callable[[], str]
    name: ClassVar[str] = "available_skills"

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        return SectionOutput(text=block("available_skills", self.catalog_skills_provider()))


def build_tools_section(config: BaseModel) -> ToolsSection:
    del config
    return ToolsSection()


def build_cloud_sandbox_section(config: BaseModel) -> CloudSandboxSection:
    del config
    return CloudSandboxSection()


def build_available_skills_section(
    config: BaseModel, *, catalog: Callable[[], str]
) -> AvailableSkillsSection:
    del config
    return AvailableSkillsSection(catalog_skills_provider=catalog)


__all__ = [
    "AvailableSkillsSection",
    "CloudSandboxSection",
    "ToolsSection",
    "build_available_skills_section",
    "build_cloud_sandbox_section",
    "build_tools_section",
]
