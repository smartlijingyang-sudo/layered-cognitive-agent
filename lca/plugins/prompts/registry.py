"""PromptSectionRegistry — Cordis plugin owning the section-collection seam."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import PROMPT_SECTION_REGISTRY
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptSectionRegistry,
    SectionKind,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class PromptSectionRegistryError(KeyError):
    """Raised when a section is registered twice under the same key."""


class _RegistryImpl(PromptSectionRegistry):
    """Closed-vocabulary registry; ``(kind, name)`` keying."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], object] = {}

    def register(self, section: object, *, kind: SectionKind, name: str) -> None:
        key = (kind, name)
        if key in self._by_key:
            raise PromptSectionRegistryError(
                f"section {name!r} ({kind}) already registered"
            )
        self._by_key[key] = section

    def resolve(self, *, kind: SectionKind, name: str) -> object | None:
        return self._by_key.get((kind, name))

    def list_sections(self) -> tuple[tuple[SectionKind, str, object], ...]:
        return tuple(
            (kind, name, self._by_key[(kind, name)])
            for (kind, name) in sorted(self._by_key)
        )


class Config(BaseModel):
    """The registry has no per-instance configuration."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-prompt-section-registry",
    Config=Config,
    provides=[PROMPT_SECTION_REGISTRY.key],
    requires=[],
    layer="L1",
    effects="none",
    description="Provide the closed registry for prompt section providers.",
    test_suite="tests/architecture/test_prompt_section_registry.py",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-prompt-section-registry.checked",
                "lca-prompt-section-registry.served",
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
    """Provide an empty PromptSectionRegistry for sections to register into."""

    del config
    ctx.provide(PROMPT_SECTION_REGISTRY.key, _RegistryImpl())


__all__ = [
    "Config",
    "PromptSectionRegistryError",
    "_RegistryImpl",
    "setup",
]
