"""Profile-selected prompt renderer for automatic Team casting."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from lca.cognition.brain.prompts import load_builtin_prompt
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import TEAM_CASTING_PROMPT_RENDERER
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.collaboration.casting import CastingPromptRenderer, RoleIndexEntry
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_OBJECTIVE_PLACEHOLDER = "{objective}"
_CATALOG_PLACEHOLDER = "{role_catalog}"


@dataclass(frozen=True, slots=True)
class BuiltinCastingPromptRenderer(CastingPromptRenderer):
    """Render the selected built-in template with a stable role catalog."""

    template_name: str = "casting_prompt"

    def render(self, objective: str, index: tuple[RoleIndexEntry, ...]) -> str:
        """Render a role catalog without allowing caller input to select a template."""

        by_department: dict[str, list[RoleIndexEntry]] = {}
        for entry in index:
            by_department.setdefault(entry.department, []).append(entry)
        lines: list[str] = []
        for department in sorted(by_department):
            lines.append(f"## {department}")
            for entry in by_department[department]:
                emoji = f"{entry.emoji} " if entry.emoji else ""
                lines.append(f"- {entry.role_id} | {emoji}{entry.title} | {entry.summary}")
        template = load_builtin_prompt(self.template_name)
        return template.replace(_CATALOG_PLACEHOLDER, "\n".join(lines)).replace(
            _OBJECTIVE_PLACEHOLDER, objective
        )


class Config(BaseModel):
    """Static built-in template selected by the profile's renderer plugin."""

    model_config = ConfigDict(extra="forbid")
    template_name: str = "casting_prompt"


@plugin(
    id="lca-team-casting-prompt-renderer-builtin",
    provides=[TEAM_CASTING_PROMPT_RENDERER.key],
    requires=[],
    implements=[CastingPromptRenderer],
    layer="L4",
    effects="none",
    description="Render the profile-selected built-in prompt for automatic Team casting.",
    test_suite="tests/architecture/test_casting_prompt_renderer_capability.py",
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-team-casting-prompt-renderer-builtin.checked",
                "lca-team-casting-prompt-renderer-builtin.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the prompt renderer used by the selected Team-caster policy."""

    ctx.provide(
        TEAM_CASTING_PROMPT_RENDERER.key, BuiltinCastingPromptRenderer(config.template_name)
    )


__all__ = ["BuiltinCastingPromptRenderer", "Config", "setup"]
