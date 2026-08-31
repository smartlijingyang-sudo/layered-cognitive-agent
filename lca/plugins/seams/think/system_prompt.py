"""System Prompt Service Definition plugin — Tier-1.

The full SystemPromptService (with section assembler) is out of scope for
this minimal stub. Real implementation lives in lca/infrastructure/system_prompt/service.py.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
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


class _MinimalSystemPromptService:
    """Minimal stub — replaced by full implementation in Chunk 2."""

    def assemble(self, role: str, **kwargs: object) -> str:
        return f"base_prompt_for({role})"


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-system-prompt-service",
    provides=["system_prompt"],
    layer="L0",
    effects="none",
    description="Minimal SystemPromptService stub — section assembler deferred.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-system-prompt-service.checked", "lca-system-prompt-service.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("system_prompt",),
        emits=("system_prompt.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    ctx.provide("system_prompt", _MinimalSystemPromptService())
