"""observation.llm_call_trace —— LLM 调用观察者。

module M5: lca/contracts/observability/observation/m5_event_traces/
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lca.contracts.observability.observation import LLMCallTrace
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.fact_gateway import append_surface_bound

_EV_LLM_CALL = "observation.llm_call"
_OBSERVER_ACTOR = "observation"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def observe_llm_call(
    *,
    run_id: str,
    source_node_id: str,
    model: str,
    prompt_digest: str,
    response_digest: str,
    token_usage: dict[str, int] | None = None,
    latency_ms: int = 0,
    cache_hit: bool = False,
    success: bool = True,
) -> None:
    fact = LLMCallTrace(
        run_id=run_id,
        source_node_id=source_node_id,
        model=model,
        prompt_digest=prompt_digest,
        response_digest=response_digest,
        token_usage=token_usage or {},
        latency_ms=latency_ms,
        cache_hit=cache_hit,
        success=success,
        occurred_at=_now_iso(),
    )
    append_surface_bound(
        _EV_LLM_CALL,
        fact.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )


@plugin(
    id="observation.llm_call_trace",
    provides=("observation.llm_call_trace",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="LLM call observer —— emit LLMCallTrace fact on each LLM call.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("observation.llm_call_trace", observe_llm_call)


__all__ = ["observe_llm_call", "setup"]
