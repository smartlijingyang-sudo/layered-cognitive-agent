"""Profile provider for session-scoped Agent-turn task ownership."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.session_turn import SessionTurnControllerFactory
from lca.harness.agent.turn_controller import InProcessSessionTurnController
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Default in-process Session turn controller configuration."""

    model_config = {"extra": "forbid"}


class InProcessSessionTurnControllerFactory(SessionTurnControllerFactory):
    """Create one cancellation-aware task controller for each live Session."""

    def create(self, *, session_id: str) -> InProcessSessionTurnController:
        return InProcessSessionTurnController(session_id=session_id)


@plugin(
    id="lca-session-turn-controller-factory",
    requires=[],
    provides=["session_turn_controller_factory"],
    implements=[SessionTurnControllerFactory],
    layer="L3",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide isolated session-turn task ownership so a Profile may replace "
        "cancellation and serialization behavior without changing a loop or carrier."
    ),
)
async def setup(ctx: PluginContext, config: object) -> None:
    """Expose the default in-process controller factory to the booted Profile."""

    del config
    ctx.provide("session_turn_controller_factory", InProcessSessionTurnControllerFactory())


__all__ = ["Config", "InProcessSessionTurnControllerFactory", "setup"]
