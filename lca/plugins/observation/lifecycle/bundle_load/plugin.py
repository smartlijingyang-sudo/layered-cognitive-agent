"""observation.lifecycle.bundle_load —— bundle / plugin 装载结果观察者。

module M4: lca/contracts/observability/observation/m4_lifecycle/
"""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.observation import BundleLoad
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.observation import now_iso, publish_ep_observation

_EV_BUNDLE_LOAD = "observation.bundle.load"


def observe_bundle_load(
    *,
    run_id: str,
    bundle_id: str,
    plugin_id: str | None = None,
    status: str,
    version: str | None = None,
    failure_reason: str | None = None,
) -> None:
    fact = BundleLoad(
        run_id=run_id,
        bundle_id=bundle_id,
        plugin_id=plugin_id,
        status=status,
        version=version,
        failure_reason=failure_reason,
        loaded_at=now_iso(),
    )
    publish_ep_observation(
        _EV_BUNDLE_LOAD,
        fact.model_dump(mode="json"),
    )


@plugin(
    id="observation.lifecycle.bundle_load",
    provides=("observation.lifecycle.bundle_load",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Bundle load observer —— emit BundleLoad fact on each bundle/plugin load.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("observation.lifecycle.bundle_load", observe_bundle_load)


__all__ = ["observe_bundle_load", "setup"]
