"""Gateway-owned registration adapter for the legacy cognitive run driver.

The driver binds Gateway run-session and carrier result types, so its registry
entry belongs to the outer composition root.  It still consumes the LCA
``run_mode_registry`` seam and exposes the same plugin identity to profiles.
"""

from __future__ import annotations

from typing import Any, cast

import structlog

from gateway.runs.loop_drivers import CognitiveRunDriver
from gateway.runs.runnable_assembly import CognitiveRunnableAssembler
from lca.contracts.capabilities import (
    RUN_MODE_REGISTRY,
    SESSION_FOLLOWUP_POLICY,
    SESSION_TURN_CONTROLLER_FACTORY,
)
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.protocols.run_mode import RunModeRegistryProtocol
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop_drivers.cognitive import build_cognitive_live_agent

_log = structlog.get_logger(__name__)


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
async def setup(ctx: PluginContext, config: dict[str, Any]) -> None:
    """Mount the cognitive live-agent factory and profile-aware run driver."""

    target = (config or {}).get("target", "cognitive") if isinstance(config, dict) else "cognitive"
    registry = ctx.require("run_loop_driver_registry")
    registry.register(target, lambda: _cognitive_driver_factory(ctx))
    ctx.provide("agent_loop", build_cognitive_live_agent)
    _log.debug("agent_loop_registered", target=target)


__all__ = ["setup"]
