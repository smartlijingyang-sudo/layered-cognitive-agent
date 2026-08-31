"""ProfileSnapshot seam plugin (Tier-1) —— ADR-0096 MVA-3.

声明 ``profile_snapshots`` 注册中心；boot 后 ``providers/profile_snapshot/run_boot``
注入 ``RunBootSnapshot`` 实现,boot 期一次性写 ``traces/runs/<id>/profile_snapshot.json``。
plugin.inventory 不再写 journal。
"""

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


@plugin(
    id="lca-profile-snapshot-seam",
    provides=["profile_snapshots"],
    requires=[],
    layer="L0",
    effects="none",
    description="Provide the profile_snapshots registry (ADR-0096 MVA-3).",
    test_suite="tests/test_profile_snapshot_seam.py::test_profile_snapshot_seam_provides_registry",
    kind=PluginKind.SEAM,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-profile-snapshot-seam.checked", "lca-profile-snapshot-seam.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("profile_snapshots",),
        emits=("profile_snapshots.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry

    ctx.provide("profile_snapshots", NamedRegistry())
