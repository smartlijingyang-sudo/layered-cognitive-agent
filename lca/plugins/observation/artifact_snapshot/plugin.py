"""observation.artifact_snapshot —— 节点退出时的完整 artifacts 快照。

module M6: lca/contracts/observability/observation/m6_artifact/

聚合策略:零 in-memory state。Caller 在 NodeExit 时刻调用本 observer,
传入当前节点累积的 artifacts dict(由 caller 自己 query Session 已
commit 的 fact 拼出来),observer 走 Session.append emit。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lca.contracts.observability.observation import ArtifactSnapshot
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.fact_gateway import append_surface_bound

_EV_ARTIFACT = "observation.artifact_snapshot"
_OBSERVER_ACTOR = "observation"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def observe_artifact_snapshot(
    *,
    run_id: str,
    node_id: str,
    phase: str,
    artifacts: dict[str, Any],
    context_digest: str | None = None,
) -> None:
    fact = ArtifactSnapshot(
        run_id=run_id,
        node_id=node_id,
        phase=phase,
        artifacts=artifacts,
        context_digest=context_digest,
        snapshotted_at=_now_iso(),
    )
    append_surface_bound(
        _EV_ARTIFACT,
        fact.model_dump(mode="json"),
        actor=_OBSERVER_ACTOR,
        surface_op="append",
        visibility="model",
    )


@plugin(
    id="observation.artifact_snapshot",
    provides=("observation.artifact_snapshot",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Artifact snapshot observer —— caller 在 NodeExit 时聚合 artifacts 并 emit.",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("observation.artifact_snapshot", observe_artifact_snapshot)


__all__ = ["observe_artifact_snapshot", "setup"]
