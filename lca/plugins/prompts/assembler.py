"""PromptAssembler — Cordis plugin that provides the section-template renderer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.cognition.brain.sections.assembler import SectionManifestPromptAssembler
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import (
    PROMPT_ASSEMBLER,
    PROMPT_SECTION_REGISTRY,
    PROMPT_TEMPLATE_PROVIDER,
)
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Profile-configurable toggles for the section-manifest assembler."""

    model_config = ConfigDict(extra="forbid")
    strip_empty_fields: bool = True


@plugin(
    id="lca-prompt-assembler-section-manifest",
    Config=Config,
    provides=[PROMPT_ASSEMBLER.key],
    requires=[PROMPT_SECTION_REGISTRY.key, PROMPT_TEMPLATE_PROVIDER.key],
    layer="L1",
    effects="none",
    description="Provide the default section-manifest PromptAssembler.",
    test_suite="tests/architecture/test_prompt_assembler_capability.py",
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
                "lca-prompt-assembler-section-manifest.checked",
                "lca-prompt-assembler-section-manifest.served",
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
    """Provide the default assembler bound to the resolved registry + provider."""

    registry = ctx.require(PROMPT_SECTION_REGISTRY.key)
    provider = ctx.require(PROMPT_TEMPLATE_PROVIDER.key)
    assembler = SectionManifestPromptAssembler(
        registry=registry,
        template_provider=provider,
        strip_empty_fields=config.strip_empty_fields,
    )
    ctx.provide(PROMPT_ASSEMBLER.key, assembler)


__all__ = ["Config", "setup"]
