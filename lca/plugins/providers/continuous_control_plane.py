"""Profile-selected durable continuous-control-plane provider."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from lca.contracts.harness.continuous import ContinuousControlPlaneFactory
from lca.harness.continuous import SqliteContinuousControlPlaneFactory
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


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
