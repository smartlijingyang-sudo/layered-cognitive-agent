"""Profile-selected durable continuous-control-plane provider."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from lca.contracts.harness.tasks.continuous import ContinuousControlPlaneFactory
from lca.harness.continuous import SqliteContinuousControlPlaneFactory
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    """Storage and worker lease policy for one deployment control plane."""

    database_path: str = ".lca/continuous-work.db"
    lease_seconds: int = Field(default=60, gt=0)
    retry_delay_seconds: float = Field(default=5.0, ge=0)

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-continuous-control-plane-factory",
    requires=[],
    provides=["continuous_control_plane_factory"],
    implements=[ContinuousControlPlaneFactory],
    layer="L3",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide durable trigger de-duplication, work leasing and bounded Session dispatch "
        "outside the closed cognitive phase graph."
    ),


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-continuous-control-plane-factory.checked', 'lca-continuous-control-plane-factory.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('continuous_control_plane_factory',),
        emits=('continuous_control_plane_factory.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose a factory so Profile selection owns control-plane storage policy."""

    ctx.provide(
        "continuous_control_plane_factory",
        SqliteContinuousControlPlaneFactory(
            database_path=Path(config.database_path),
            lease_seconds=config.lease_seconds,
            retry_delay_seconds=config.retry_delay_seconds,
        ),
    )


__all__ = ["Config", "setup"]
