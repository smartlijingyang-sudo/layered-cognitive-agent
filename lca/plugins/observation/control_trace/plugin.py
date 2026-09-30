"""observation.control_trace —— 控制面事件观察者。

module M5: lca/contracts/observability/observation/m5_event_traces/

Emit 走 :func:`append_catalog_bound` —— Session 单轨（ADR-0186）。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.observation import ControlTrace
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.observation import now_iso, publish_session_observation
from lca.plugins.events._session_observe import current_session


def observe_control(
    *,
    run_id: str,
    source_node_id: str,
    control_slot: str,
    verdict: str,
    reason: str | None = None,
    contract_clause: str | None = None,
    observed_value: dict[str, Any] | None = None,
) -> None:
    fact = ControlTrace(
        run_id=run_id,
        source_node_id=source_node_id,
        control_slot=control_slot,
        verdict=verdict,
        reason=reason,
        contract_clause=contract_clause,
        observed_value=observed_value,
        occurred_at=now_iso(),
    )
    publish_session_observation(fact, session=current_session())


@plugin(
    id="observation.control_trace",
    provides=("observation.control_trace",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Control observer —— emit ControlTrace fact on each control verdict.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("observation.control_trace", observe_control)


__all__ = ["observe_control", "setup"]
