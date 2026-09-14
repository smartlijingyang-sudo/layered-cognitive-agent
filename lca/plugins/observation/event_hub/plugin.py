"""observation.event_hub —— SPINE EP → observer capability 的调度层。

Bundle 内自装配,职责单一:fan-out 已存在 SPINE EP 到对应的 observer capability。
- 不调 Session.append / EventSpine.append / FactGateway / publish_ep_bound
  —— emit 路径完全由被调度的 observer 内部 append_surface_bound 负责。
- 不直连 Session / journal backends —— 只订阅 EventSpine。
- 不重写 graph framework / runtime emit 路径 —— 只追加 fan-out。
- plugin 间不直接 import —— 通过 ctx.require("event_spine") + ctx.require(observer_capability_key) 通信。

Contract 在 lca/contracts/observability/observation/m0_event_hub/。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from lca.contracts.observability.observation import (
    EventHubConfig,
    FanoutRule,
    validate_fanout_table,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.event.spine import EventSpine

log = logging.getLogger(__name__)


# SPINE EP → observer capability 静态映射表(只覆盖 runtime 已经主动 emit 的 EP)。
# 其余 9 类 observation fact 在各 driver / lifecycle 调用方显式 ctx.require(observer_capability_key)(...),
# 不走 hub fan-out —— 后续 PR 在 EP_FANOUT_TABLE 加 enabled rule。
_EP_FANOUT_TABLE: EventHubConfig = EventHubConfig(
    rules=(
        FanoutRule(
            ep="phase_graph.node.start",
            observer_capability="observation.node_enter",
        ),
        FanoutRule(
            ep="phase_graph.node.end",
            observer_capability="observation.node_exit",
        ),
        FanoutRule(
            ep="runtime.reducer.apply",
            observer_capability="observation.runtime_bookkeeping",
        ),
    ),
)


def _build_ep_index(
    config: EventHubConfig,
) -> dict[str, str]:
    """EP → observer capability key 的 lookup index。

    只在 setup 阶段构造一次,fan-out 走 O(1) 查表。
    """
    validate_fanout_table(config.rules)
    return {rule.ep: rule.observer_capability for rule in config.rules if rule.enabled}


def make_dispatch_fn(
    *,
    ep_index: dict[str, str],
    observers: dict[str, Callable[..., None]],
    event_spine: EventSpine,
) -> Callable[[Any], None]:
    """构造 dispatch 闭包 —— 给 EventSpine.subscribe() 用。

    不持有 module 状态;所有依赖由参数注入。try/except 隔离每个 observer 失败,
    不让单个 observer 抛错污染 EventSpine 主 emit 路径。
    """

    def dispatch(record: Any) -> None:
        ep = getattr(record, "execution_point", None)
        if not isinstance(ep, str):
            return
        capability_key = ep_index.get(ep)
        if capability_key is None:
            return
        observer = observers.get(capability_key)
        if observer is None:
            log.warning(
                "event_hub: EP %s mapped to %s but observer not registered; "
                "check bundle plugin order (observers must load before event_hub)",
                ep,
                capability_key,
            )
            return
        payload = getattr(record, "payload", None)
        try:
            observer(run_id=_extract_run_id(record), payload=payload, record=record)
        except Exception:
            log.exception(
                "event_hub: observer %s raised for ep=%s; continuing",
                capability_key,
                ep,
            )

    return dispatch


def _extract_run_id(record: Any) -> str | None:
    """从 SPINE record 提 run_id,找不到返回 None 让 observer 自行处理。"""
    return getattr(record, "run_id", None) or getattr(record, "ref_run_id", None)


@plugin(
    id="observation.event_hub",
    provides=("observation.event_hub",),
    requires=(
        "event_spine",
        "observation.node_enter",
        "observation.node_exit",
        "observation.runtime_bookkeeping",
    ),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Event hub —— fan-out SPINE EP (phase_graph.node.start/end + "
        "runtime.reducer.apply) 到对应 observer capability,触发其内部 "
        "append_surface_bound 单轨 emit。hub 自己不 emit 任何事件。"
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """订阅 EventSpine,fan-out EP → observer capability。

    不直接调 EventSpine.append / Session.append / FactGateway /
    publish_ep_bound;emit 路径完全由 observer 内部 append_surface_bound 承担。
    """
    del config
    event_spine: EventSpine = ctx.require("event_spine")
    observers: dict[str, Callable[..., None]] = {
        "observation.node_enter": ctx.require("observation.node_enter"),
        "observation.node_exit": ctx.require("observation.node_exit"),
        "observation.runtime_bookkeeping": ctx.require("observation.runtime_bookkeeping"),
    }
    ep_index = _build_ep_index(_EP_FANOUT_TABLE)
    dispatch = make_dispatch_fn(
        ep_index=ep_index,
        observers=observers,
        event_spine=event_spine,
    )
    unsubscribe = event_spine.subscribe(dispatch)
    ctx.provide(
        "observation.event_hub",
        {
            "dispatch": dispatch,
            "unsubscribe": unsubscribe,
            "ep_index": ep_index,
        },
    )


__all__ = [
    "_EP_FANOUT_TABLE",
    "make_dispatch_fn",
    "setup",
]

