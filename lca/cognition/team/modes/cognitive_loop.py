"""Gateway-owned registration adapter for the legacy cognitive run driver.

The driver binds Gateway run-session and carrier result types, so its registry
entry belongs to the outer composition root.  It still consumes the LCA
``run_mode_registry`` seam and exposes the same plugin identity to profiles.
"""

from __future__ import annotations

from typing import cast

import structlog
from pydantic import BaseModel, ConfigDict

from lca.contracts.capabilities import (
    RUN_MODE_REGISTRY,
    SESSION_FOLLOWUP_POLICY,
    SESSION_TURN_CONTROLLER_FACTORY,
)
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.protocols.session.run_mode import RunModeRegistryProtocol
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop_drivers.cognitive import build_cognitive_live_agent
from lca.plugins.transport.webserver.handlers.runs.execute.loop_drivers import CognitiveRunDriver
from lca.plugins.transport.webserver.handlers.runs.lifecycle.runnable_assembly import (
    CognitiveRunnableAssembler,
)

_log = structlog.get_logger(__name__)


class Config(BaseModel):
    """Pydantic config for ``lca-loop-cognitive``."""

    model_config = ConfigDict(extra="forbid")
    target: str = "cognitive"


def _cognitive_driver_factory(ctx: object) -> CognitiveRunDriver:
    """Build the Gateway driver with the Profile's declared mode registry.

    ``lca-loop-cognitive`` declares ``run_mode_registry`` as a required
    capability. Resolving it here keeps the executable driver aligned with
    that manifest: a profile that boots cannot silently select compatibility
    mode adapters through an absent registry.
    """

    registry = cast("RunModeRegistryProtocol", require_capability(ctx, RUN_MODE_REGISTRY.key))
    return CognitiveRunDriver(CognitiveRunnableAssembler(mode_registry=registry))


@plugin(
    id="lca-loop-cognitive",
    Config=Config,
    requires=[
        "run_loop_driver_registry",
        RUN_MODE_REGISTRY.key,
        SESSION_TURN_CONTROLLER_FACTORY.key,
        SESSION_FOLLOWUP_POLICY.key,
    ],
    provides=["agent_loop", "run_loop_driver_registry[cognitive]"],
    implements=[],
    layer="L4",
    effects="none",
    description="Register the Gateway-owned cognitive RunLoopDriver adapter.",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Mount the cognitive live-agent factory and profile-aware run driver."""

    registry = ctx.require("run_loop_driver_registry")
    registry.register(config.target, lambda: _cognitive_driver_factory(ctx))
    ctx.provide("agent_loop", build_cognitive_live_agent)
    _log.debug("agent_loop_registered", target=config.target)


__all__ = ["Config", "setup"]
