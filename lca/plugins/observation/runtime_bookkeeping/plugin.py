"""observation.runtime_bookkeeping —— reducer apply 观察者(默认 verbose)。

module M5: lca/contracts/observability/observation/m5_event_traces/

verbose 默认 = 全量 emit。用户原则:"日志多没事,agent-friendly"。
Emit 走 :func:`append_catalog_bound` —— Session 单轨（ADR-0186）。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.observation import ReducerApply
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.observation import now_iso, publish_session_observation
from lca.plugins.events._session_observe import current_session


def observe_reducer_apply(
    *,
    run_id: str,
    method: str,
    outcome: str,
    args_digest: str | None = None,
    state_diff_digest: str | None = None,
    exception_class: str | None = None,
    phase_boundary: bool = False,
    elapsed_ms: int = 0,
) -> None:
    fact = ReducerApply(
        run_id=run_id,
        method=method,
        outcome=outcome,
        args_digest=args_digest,
        state_diff_digest=state_diff_digest,
        exception_class=exception_class,
        phase_boundary=phase_boundary,
        elapsed_ms=elapsed_ms,
        occurred_at=now_iso(),
    )
    publish_session_observation(fact, session=current_session())


@plugin(
    id="observation.runtime_bookkeeping",
    provides=("observation.runtime_bookkeeping",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Reducer apply observer (verbose 全量) —— "
        "emit ReducerApply fact on every reducer.apply_* call."
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide("observation.runtime_bookkeeping", observe_reducer_apply)


__all__ = ["observe_reducer_apply", "setup"]
