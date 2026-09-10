"""observation.decision_trace —— 决策产生 / 拒绝的观察者。

module M5: lca/contracts/observability/observation/m5_event_traces/
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lca.contracts.observability.observation import DecisionTrace
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.fact_gateway import append_surface_bound

_EV_DECISION = "observation.decision"
_OBSERVER_ACTOR = "observation"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def observe_decision(
    *,
    run_id: str,
    decision_id: str,
    source_node_id: str,
    accepted: bool,
    action_type: str | None = None,
    payload: dict[str, Any] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    chosen_index: int | None = None,
    rationale: str | None = None,
) -> None:
    fact = DecisionTrace(
        run_id=run_id,
        decision_id=decision_id,
        source_node_id=source_node_id,
        action_type=action_type,
        payload=payload or {},
        candidates=tuple(candidates or ()),
        chosen_index=chosen_index,
        rationale=rationale,
        accepted=accepted,
        occurred_at=_now_iso(),
    )
    append_surface_bound(
        _EV_DECISION,
        fact.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )


@plugin(
    id="observation.decision_trace",
    provides=("observation.decision_trace",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Decision observer —— emit DecisionTrace fact on each decision.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("observation.decision_trace", observe_decision)


__all__ = ["observe_decision", "setup"]
