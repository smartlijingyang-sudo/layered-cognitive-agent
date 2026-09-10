"""observation.node_trajectory —— 节点进入 / 退出的观察者。

modules M2 (NodeEnter) + M3 (NodeExit):
  lca/contracts/observability/observation/m2_node_input/
  lca/contracts/observability/observation/m3_node_output/

Observer 函数,零 class wrapper;caller 直接调用。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lca.contracts.observability.observation import (
    NodeEnter,
    NodeException,
    NodeExit,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.fact_gateway import append_surface_bound

_EV_NODE_ENTER = "observation.node_enter"
_EV_NODE_EXIT = "observation.node_exit"
_OBSERVER_ACTOR = "observation"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def observe_node_enter(
    *,
    run_id: str,
    node_id: str,
    phase: str,
    binding: str | None = None,
    parent_node_id: str | None = None,
    sub_graph_id: str | None = None,
    depth: int = 0,
    visit_count: int = 1,
    inputs: dict[str, Any] | None = None,
) -> None:
    fact = NodeEnter(
        run_id=run_id,
        node_id=node_id,
        phase=phase,
        binding=binding,
        parent_node_id=parent_node_id,
        sub_graph_id=sub_graph_id,
        depth=depth,
        visit_count=visit_count,
        entered_at=_now_iso(),
        inputs=inputs or {},
    )
    append_surface_bound(
        _EV_NODE_ENTER,
        fact.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )


def observe_node_exit(
    *,
    run_id: str,
    node_id: str,
    phase: str,
    binding: str | None = None,
    parent_node_id: str | None = None,
    sub_graph_id: str | None = None,
    exit_status: str = "success",
    elapsed_ms: int = 0,
    outputs: dict[str, Any] | None = None,
    exception: NodeException | None = None,
) -> None:
    fact = NodeExit(
        run_id=run_id,
        node_id=node_id,
        phase=phase,
        binding=binding,
        parent_node_id=parent_node_id,
        sub_graph_id=sub_graph_id,
        exit_status=exit_status,
        elapsed_ms=elapsed_ms,
        outputs=outputs or {},
        exception=exception,
        exited_at=_now_iso(),
    )
    append_surface_bound(
        _EV_NODE_EXIT,
        fact.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )


@plugin(
    id="observation.node_trajectory",
    provides=("observation.node_enter", "observation.node_exit"),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Node enter/exit observer —— emit NodeEnter / NodeExit fact.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("observation.node_enter", observe_node_enter)
    ctx.provide("observation.node_exit", observe_node_exit)


__all__ = ["observe_node_enter", "observe_node_exit", "setup"]
