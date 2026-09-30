"""observation.node_trajectory —— 节点进入 / 退出的观察者。

modules M2 (NodeEnter) + M3 (NodeExit):
  lca/contracts/observability/observation/m2_node_input/
  lca/contracts/observability/observation/m3_node_output/

Observer 函数,零 class wrapper;caller 直接调用。
Emit 走 :func:`append_catalog_bound` —— Session 单轨（ADR-0186）。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.observation import (
    NodeEnter,
    NodeException,
    NodeExit,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.observation import now_iso, publish_session_observation
from lca.plugins.events._session_observe import current_session


def observe_node_enter(
    *,
    run_id: str,
    node_id: str,
    phase: str = "",
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
        entered_at=now_iso(),
        inputs=inputs or {},
    )
    publish_session_observation(fact, session=current_session())


def observe_node_exit(
    *,
    run_id: str,
    node_id: str,
    phase: str = "",
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
        exited_at=now_iso(),
    )
    publish_session_observation(fact, session=current_session())


@plugin(
    id="observation.node_trajectory",
    provides=("observation.node_enter", "observation.node_exit"),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Node enter/exit observer —— emit NodeEnter / NodeExit fact via Session SSOT.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("observation.node_enter", observe_node_enter)
    ctx.provide("observation.node_exit", observe_node_exit)


__all__ = ["observe_node_enter", "observe_node_exit", "setup"]
