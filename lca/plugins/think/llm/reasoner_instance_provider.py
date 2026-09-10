"""Inner-subgraph ``reasoner`` capability plugin.

Builds a :class:`lca.cognition.brain.reasoner.reasoner.PromptReasoner`
instance from the active :class:`LLMResolver` and registers it on the
``reasoner`` capability key. Inner-subgraph node plugins
(``think.reason.plan`` / ``.render`` / ``.complete``) read this via
``context.runtime.reasoner``; the framework's
:class:`NodeRuntimeView` translates that into a
``ctx.require("reasoner")`` call.

Distinction from ``lca-reasoner-prompt``:

- ``lca-reasoner-prompt`` (``reasoner.prompt``) provides the
  :class:`PromptReasoner` **class** so ``SimpleBrainFactory`` can
  instantiate it per-call with the right outer wiring.
- This plugin (``reasoner``) provides a single configured
  :class:`PromptReasoner` **instance** with the resolved LLM
  adapter already bound; the inner subgraph reuses this instance
  across plan / render / complete calls.

Boundary:

- This plugin owns the conversion from ``LLMResolver`` to a bound
  ``PromptReasoner``; it does not own credential loading or
  provider fallback (those live in the resolver plugin).
- The role profile is intentionally minimal — the inner subgraph
  renders prompts through this reasoner's role, not directly. If a
  profile needs richer role wiring, it can provide a different
  binding via ``ctx.provide("reasoner", MyReasoner(...))``.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.mechanisms.capability.capability import require_capability
from lca.contracts.protocols import Reasoner
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="phase.think.reasoner",
    provides=("reasoner",),
    requires=("llm_resolver",),
    implements=[Reasoner],
    layer="L1",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide a configured PromptReasoner instance as the inner-"
        "subgraph ``reasoner`` capability. Built from the active "
        "LLMResolver adapter; node plugins read it via "
        "``context.runtime.reasoner``."
    ),
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
                "phase_think_reasoner.checked",
                "phase_think_reasoner.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("llm_resolver",),
        emits=("reasoner.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Build a PromptReasoner instance bound to the LLMResolver adapter.

    The role profile fields are intentionally minimal; the inner
    subgraph's prompt assembler / template selector supply the
    real per-call content. The reasoner only owns ``build_turn_plan``
    / ``render_turn`` / ``complete_turn`` mechanics and the bound
    ``llm`` adapter.
    """
    del config
    from lca.cognition.brain.reasoner.reasoner import PromptReasoner
    from lca.contracts.models.team.role.team import (
        RoleProfile,
        ToolPermissionManifest,
    )

    llm_resolver = require_capability(ctx, "llm_resolver")
    adapter = llm_resolver.resolve()
    role_profile = RoleProfile(
        role="assistant",
        goal="answer user questions",
        backstory="LCA inner think subgraph reasoner",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    ctx.provide("reasoner", PromptReasoner(llm=adapter, role_profile=role_profile))


__all__ = ["Config", "setup"]
