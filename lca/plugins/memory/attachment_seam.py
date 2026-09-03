"""Attachment Service Definition plugin — Tier-1."""

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
from lca.contracts.protocols.runtime.infra import AttachmentIdentity
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class AttachmentService:
    """Service Definition for attachment identity.

    Holds a registry of AttachmentIdentity providers. The active one is
    selected at boot time; the provider used at run time is `current()`.
    """

    def __init__(self) -> None:
        self._providers: dict[str, AttachmentIdentity] = {}
        self._active: str | None = None

    def register(self, name: str, provider: AttachmentIdentity, *, activate: bool = False) -> None:
        self._providers[name] = provider
        if activate or self._active is None:
            self._active = name

    def current(self) -> AttachmentIdentity | None:
        if self._active is None:
            return None
        return self._providers.get(self._active)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-attachment-service",
    provides=["attachment"],
    implements=[AttachmentIdentity],
    layer="L0",
    effects="world",
    description="Provide the Attachment Definition service (ProviderDispatch + attachment identity table).",
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
            descriptors=("lca-attachment-service.checked", "lca-attachment-service.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("attachment",),
        emits=("attachment.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    ctx.provide("attachment", AttachmentService())
