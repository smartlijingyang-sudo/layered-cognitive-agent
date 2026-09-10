"""observation.lifecycle.subgraph_resolve —— sub_spec_ref 解析结果观察者。

module M4: lca/contracts/observability/observation/m4_lifecycle/

外层 wrap:SubgraphRunner 入口包 try/except,把解析结果走 Session.append emit。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lca.contracts.observability.observation import SubgraphResolve
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.fact_gateway import append_surface_bound

_EV_SUBGRAPH = "observation.subgraph.resolve"
_OBSERVER_ACTOR = "observation"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def observe_subgraph_resolve(
    *,
    run_id: str,
    plan_ref: str,
    owner_node_id: str,
    entry_node: str,
    status: str,
    sub_blueprint_digest: str | None = None,
    failure_reason: str | None = None,
) -> None:
    fact = SubgraphResolve(
        run_id=run_id,
        plan_ref=plan_ref,
        owner_node_id=owner_node_id,
        entry_node=entry_node,
        status=status,
        sub_blueprint_digest=sub_blueprint_digest,
        failure_reason=failure_reason,
        resolved_at=_now_iso(),
    )
    append_surface_bound(
        _EV_SUBGRAPH,
        fact.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )


@plugin(
    id="observation.lifecycle.subgraph_resolve",
    provides=("observation.subgraph_resolve",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Subgraph resolve observer —— emit SubgraphResolve fact.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("observation.subgraph_resolve", observe_subgraph_resolve)


__all__ = ["observe_subgraph_resolve", "setup"]
