"""observation.event_hub —— SPINE-shape SessionEvent → observer capability 调度层.

Bundle 内自装配;职责单一:fan-out SPINE-shape SessionEvent 到对应 observer capability.
- 不调 Session.append / EventSpine.append / FactGateway / publish_ep_bound
- 不直连 Session 后端或 journal backends
- plugin 间不直接 import —— 通过 ctx.require 通信

为什么不用 EventSpine.subscribe:
    wrap_instrument 走 ``spine.append → spine_port_append → session_hook``.
    而 ``make_session_spine_append_hook`` (ADR-0186 Session SSOT) 内部
    ``del sinks, subscribers`` 直接丢弃 subscriber 列表,
    走 ``bridge.append(SpineEventPayload)`` 单轨. 所以 EventSpine.subscribe
    的 callback 在 ADR-0186 之后永远不会被调. 必须订阅 Session observer
    才能在 Session.append 路径上拿到事件. 详见
    lca/plugins/session/spine_anomaly/spine_anomaly.py 的 canonical pattern.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from lca.contracts.observability.observation import (
    EventHubConfig,
    FanoutRule,
    validate_fanout_table,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.session.runtime.spine.event_projection import (
    session_event_to_event_record,
)

log = logging.getLogger(__name__)


_EP_FANOUT_TABLE: EventHubConfig = EventHubConfig(
    rules=(
        FanoutRule(ep="phase_graph.node.start", observer_capability="observation.node_enter"),
        FanoutRule(ep="phase_graph.node.end", observer_capability="observation.node_exit"),
        FanoutRule(
            ep="runtime.reducer.apply", observer_capability="observation.runtime_bookkeeping"
        ),
    ),
)


def _build_ep_index(config: EventHubConfig) -> dict[str, str]:
    validate_fanout_table(config.rules)
    return {rule.ep: rule.observer_capability for rule in config.rules if rule.enabled}


def _invoke_observer(observer: Callable[..., None], record: Any) -> None:
    """Adapter: SPINE-shape EventRecord → observer function kwargs.

    Each observer has its own signature; use a small switch keyed by
    execution_point. 这是唯一把 record payload dict 拆成 kwargs 的地方;
    plugin 间不直接 import —— 只拿 observer callable, 不拿它的 module.
    """
    ep = getattr(record, "execution_point", "")
    payload = getattr(record, "payload", {}) or {}
    if ep == "phase_graph.node.start":
        observer(
            run_id=getattr(record, "run_id", None),
            node_id=payload.get("node_id"),
            phase=payload.get("phase"),
            binding=payload.get("binding"),
            parent_node_id=payload.get("parent_node_id"),
            sub_graph_id=payload.get("sub_graph_id"),
            depth=payload.get("depth", 0),
            visit_count=payload.get("visit_count", 1),
            inputs=payload.get("inputs", {}),
        )
    elif ep == "phase_graph.node.end":
        observer(
            run_id=getattr(record, "run_id", None),
            node_id=payload.get("node_id"),
            phase=payload.get("phase"),
            binding=payload.get("binding"),
            parent_node_id=payload.get("parent_node_id"),
            sub_graph_id=payload.get("sub_graph_id"),
            exit_status=payload.get("exit_status", "success"),
            elapsed_ms=payload.get("elapsed_ms", 0),
            outputs=payload.get("outputs", {}),
        )
    elif ep == "runtime.reducer.apply":
        observer(
            run_id=getattr(record, "run_id", None),
            reducer=payload.get("reducer"),
            phase=payload.get("phase"),
            seq=payload.get("seq"),
            payload=payload,
        )
    else:
        log.warning("event_hub: unknown EP %s reached _invoke_observer", ep)


def make_dispatch_fn(
    *,
    ep_index: dict[str, str],
    observers: dict[str, Callable[..., None]],
) -> Callable[[Any, Any], None]:
    """构造 Session observer —— 给 SessionStore.add_observer_hook + session.observe 用.

    observer 签名: (session, SessionEvent) -> None. 不持有 module 状态,
    所有依赖由参数注入.
    """

    def dispatch(session: Any, event: Any) -> None:
        record = session_event_to_event_record(session, event)
        if record is None:
            return
        ep = getattr(record, "execution_point", None)
        if not isinstance(ep, str):
            return
        capability_key = ep_index.get(ep)
        if capability_key is None:
            return
        observer = observers.get(capability_key)
        if observer is None:
            log.warning(
                "event_hub: EP %s mapped to %s but observer not registered",
                ep,
                capability_key,
            )
            return
        try:
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon(_invoke_observer, observer, record)
            except RuntimeError:
                _invoke_observer(observer, record)
        except Exception:
            log.exception("event_hub: dispatch deferred-call setup failed for ep=%s", ep)

    return dispatch


@plugin(
    id="observation.event_hub",
    provides=("observation.event_hub",),
    requires=(
        "session.store",
        "observation.node_enter",
        "observation.node_exit",
        "observation.runtime_bookkeeping",
    ),
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Event hub —— fan-out SPINE-shape SessionEvent (phase_graph.node.start/end "
        "+ runtime.reducer.apply) 到对应 observer capability,触发其内部 "
        "publish_ep_bound 单轨 emit。hub 自己不 emit 任何事件。L2 因为 "
        "requires 同层 spine_anomaly 用的 session.store."
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """注册 Session observer 触发器.

    走两条路:
    1. SessionStore.add_observer_hook —— 未来创建的 Session 都自动 observe(dispatch)
    2. store.list() —— 当前活 Session 也补 attach (hub 装载晚于 Session 创建的场景)
    """
    del config
    store = ctx.require("session.store")
    observers: dict[str, Callable[..., None]] = {
        "observation.node_enter": ctx.require("observation.node_enter"),
        "observation.node_exit": ctx.require("observation.node_exit"),
        "observation.runtime_bookkeeping": ctx.require("observation.runtime_bookkeeping"),
    }
    ep_index = _build_ep_index(_EP_FANOUT_TABLE)
    dispatch = make_dispatch_fn(ep_index=ep_index, observers=observers)

    def _attach(session: Any) -> None:
        try:
            session.observe(dispatch)
        except Exception:
            log.exception("event_hub: session.observe attach failed")

    cancel_creation = store.add_observer_hook(_attach)
    for session in getattr(store, "list", lambda: ())():
        _attach(session)
    ctx.provide(
        "observation.event_hub",
        {"dispatch": dispatch, "cancel_creation": cancel_creation, "ep_index": ep_index},
    )


__all__ = [
    "_EP_FANOUT_TABLE",
    "make_dispatch_fn",
    "setup",
]
