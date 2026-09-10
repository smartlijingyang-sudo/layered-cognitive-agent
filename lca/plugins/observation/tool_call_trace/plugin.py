"""observation.tool_call_trace —— 工具调用观察者。

module M5: lca/contracts/observability/observation/m5_event_traces/
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lca.contracts.observability.observation import ToolCallTrace
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.fact_gateway import append_surface_bound

_EV_TOOL_CALL = "observation.tool_call"
_OBSERVER_ACTOR = "observation"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def observe_tool_call(
    *,
    run_id: str,
    source_node_id: str,
    tool_name: str,
    args: dict[str, Any],
    result: dict[str, Any] | None = None,
    success: bool = True,
    elapsed_ms: int = 0,
    retry_count: int = 0,
) -> None:
    fact = ToolCallTrace(
        run_id=run_id,
        source_node_id=source_node_id,
        tool_name=tool_name,
        args=args,
        result=result,
        success=success,
        elapsed_ms=elapsed_ms,
        retry_count=retry_count,
        occurred_at=_now_iso(),
    )
    append_surface_bound(
        _EV_TOOL_CALL,
        fact.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )


@plugin(
    id="observation.tool_call_trace",
    provides=("observation.tool_call_trace",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Tool call observer —— emit ToolCallTrace fact on each tool call.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("observation.tool_call_trace", observe_tool_call)


__all__ = ["observe_tool_call", "setup"]
