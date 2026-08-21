"""DSH loop plugin — registers the DSH ``RunLoopDriver`` into the runtime
registry. ADR-0062 §6 / PR-5: driver implementation lives in the gateway;
this plugin declares the dependency on the runtime registry and uses a
zero-arg factory so the gateway module is never imported at plugin load.
"""

from __future__ import annotations

from typing import Any

import structlog

from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_log = structlog.get_logger(__name__)


def _dsh_driver_factory() -> Any:
    from gateway.runs.loop_drivers import DshRunDriver

    return DshRunDriver()


@plugin(
    id="lca-loop-dsh",
    requires=["run_loop_driver_registry"],
    provides=["run_loop_driver_registry[dsh]"],
    implements=[],
    layer="L1",
    effects="none",
    description=(
        "Register the DSH RunLoopDriver. Loaded only by bundles that need "
        "the DSH path (e.g. ``scenario-dsh.yaml``). Omit from bundles where "
        "DSH is not deployed to keep the registry minimal."
    ),
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: dict[str, Any]) -> None:
    target = (config or {}).get("target", "dsh") if isinstance(config, dict) else "dsh"
    registry = ctx.inject("run_loop_driver_registry")
    registry.register(target, _dsh_driver_factory)
    _log.debug("dsh_driver_registered", target=target)
