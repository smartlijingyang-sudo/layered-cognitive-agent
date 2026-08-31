"""Workspace Service Definition plugin — Tier-1 (minimal stub)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


class WorkspaceService:
    """Minimal stub — full WorkspaceService deferred to follow-up.

    Holds a registry of workspace providers (currently empty).
    """

    def __init__(self) -> None:
        self._providers: dict[str, object] = {}
        self._active: str | None = None

    def register(self, name: str, provider: object, *, activate: bool = False) -> None:
        self._providers[name] = provider
        if activate or self._active is None:
            self._active = name

    def current(self) -> object | None:
        if self._active is None:
            return None
        return self._providers.get(self._active)


@plugin(
    id="lca-workspace-service",
    provides=["workspace"],
    layer="L0",
    effects="none",
    description="Minimal WorkspaceService stub — full implementation deferred.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-workspace-service.checked", "lca-workspace-service.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("workspace",),
        emits=("workspace.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    ctx.provide("workspace", WorkspaceService())
