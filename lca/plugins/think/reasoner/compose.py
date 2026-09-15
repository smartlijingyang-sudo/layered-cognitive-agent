"""phase.think.reasoner.compose — Cordis provider for PromptReasoner ports.

Boot-boundary construction only (SRP): inject ``llm_adapter``,
``prompt_template_provider``, and ``prompt_template_selector``, then publish
the ``reasoner`` capability. Role identity and per-turn tools are **not**
assembled here — they arrive as boundary DTOs
(``RoleSnapshot`` / ``ForkedTools``) on ``render_turn`` / ``complete_turn``
via ``concept.role.snapshot`` and ``concept.tool.fork``
(eng/retire-v1-reasoner-sandbox / ADR-0220 §6).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import (
    PROMPT_SECTION_REGISTRY,
    PROMPT_TEMPLATE_PROVIDER,
    PROMPT_TEMPLATE_SELECTOR,
)
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols import Reasoner
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="phase.think.reasoner.compose",
    provides=("reasoner",),
    requires=(
        "llm_adapter",
        PROMPT_SECTION_REGISTRY.key,
        PROMPT_TEMPLATE_PROVIDER.key,
        PROMPT_TEMPLATE_SELECTOR.key,
    ),
    implements=[Reasoner],
    layer="L1",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Compose a PromptReasoner from injected llm_adapter + template "
        "ports; publish as the ``reasoner`` capability. RoleSnapshot / "
        "ForkedTools arrive as turn boundary DTOs (not assembled here)."
    ),
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
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
                "phase_think_reasoner_compose.checked",
                "phase_think_reasoner_compose.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(
            "plugin.serve",
            "llm_adapter",
            PROMPT_SECTION_REGISTRY.key,
            PROMPT_TEMPLATE_PROVIDER.key,
            PROMPT_TEMPLATE_SELECTOR.key,
        ),
        emits=("reasoner.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Construct :class:`PromptReasoner` from ports and publish ``reasoner``."""
    from lca.cognition.brain.reasoner.reasoner import PromptReasoner

    del config

    adapter = ctx.require("llm_adapter")
    template_provider = ctx.require(PROMPT_TEMPLATE_PROVIDER.key)
    selector = ctx.require(PROMPT_TEMPLATE_SELECTOR.key)
    section_registry = ctx.require(PROMPT_SECTION_REGISTRY.key)

    reasoner = PromptReasoner(
        llm=adapter,
        selector=selector,
        template_provider=template_provider,
        section_registry=section_registry,
    )
    ctx.provide("reasoner", reasoner)


__all__ = ["Config", "setup"]
