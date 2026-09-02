"""PromptTemplateSelector — picks the active template id per AgentState.

The selector is a tiny pure function: ``state.active_template`` wins
(SkillRouter / test override), then ``team_awareness.consult_duty``
forces ``hierarchical_prompt``, otherwise ``routing_prompt`` for team
runs and the profile default for solo runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import PROMPT_TEMPLATE_SELECTOR
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplateSelector as Protocol_,
)
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_HIERARCHICAL = "hierarchical_prompt"
_ROUTING = "routing_prompt"
_REACT = "react_prompt"


@dataclass(frozen=True, slots=True)
class TeamAwarenessTemplateSelector(Protocol_):
    """Profile-selected selector: consult_duty → hierarchical, else routing."""

    default_template: str = _REACT

    def select(self, *, state: AgentState) -> str:
        active = getattr(state, "active_template", None)
        if isinstance(active, str) and active:
            return active
        awareness = state.team_awareness
        if awareness is None:
            return self.default_template
        if awareness.consult_duty is not None:
            return _HIERARCHICAL
        return _ROUTING


class Config(BaseModel):
    """Profile-declared default template id when no awareness / override is present."""

    model_config = ConfigDict(extra="forbid")
    default_template: str = _REACT

    def model_post_init(self, __context: object) -> None:
        if self.default_template not in {_HIERARCHICAL, _ROUTING, _REACT}:
            raise ValueError(
                f"unknown prompt template id: {self.default_template!r}; "
                f"choose one of {_HIERARCHICAL!r}, {_ROUTING!r}, {_REACT!r}"
            )


@plugin(
    id="lca-prompt-template-selector-team-awareness",
    Config=Config,
    provides=[PROMPT_TEMPLATE_SELECTOR.key],
    requires=[],
    layer="L1",
    effects="none",
    description="Pick the active template per AgentState (consult / routing / solo).",
    test_suite="tests/architecture/test_prompt_template_selector_capability.py",
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G5_COGNITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-prompt-template-selector-team-awareness.checked",
                "lca-prompt-template-selector-team-awareness.served",
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
    """Provide the team-awareness-driven selector."""

    ctx.provide(
        PROMPT_TEMPLATE_SELECTOR.key,
        TeamAwarenessTemplateSelector(default_template=config.default_template),
    )


__all__ = ["Config", "TeamAwarenessTemplateSelector", "setup"]
