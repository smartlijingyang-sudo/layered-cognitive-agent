"""SimpleEventBus —— 异步事件广播 + waterfall/serial 分发（ADR-dsh-fusion）。

三种分发模式：
- ``emit``：fire-and-forget 广播（观察者模式），listener 不可拦截。
- ``waterfall``：around-middleware 链——listener 收到 ``(payload, next)``，
  调用 ``next()`` 交给下一个；不调用 = 短路。用于权限/策略/Hook 拦截链。
- ``serial``：串行决策链——listener 收到 payload 返回新 payload，
  最后一个 listener 的值胜出。用于 "last-listener-wins" 决策。

设计来源：DSH Cordis 四模分发（emit/waterfall/parallel/serial）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.protocols import EventBus

# Waterfall listener: (payload, next_fn) -> payload
WaterfallListener = Callable[[Any, Callable[[Any], Awaitable[Any]]], Awaitable[Any]]
# Serial listener: payload -> payload
SerialListener = Callable[[Any], Awaitable[Any]]


class SimpleEventBus(EventBus):
    """基于字典的事件总线：emit + waterfall + serial 三种分发。"""

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Any], Awaitable[None]]]] = {}
        self._waterfall_subs: dict[str, list[WaterfallListener]] = {}
        self._serial_subs: dict[str, list[SerialListener]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # ── emit（fire-and-forget）──────────────────────────

    def emit(self, event_name: str, payload: Any, trace_id: str) -> None:
        event_payload = {
            "event_name": event_name,
            "payload": payload,
            "trace_id": trace_id,
        }
        for handler in self._subs.get(event_name, []):
            task = asyncio.create_task(self._invoke(handler, event_payload))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _invoke(
        self, handler: Callable[[Any], Awaitable[None]], payload: dict[str, Any]
    ) -> None:
        await handler(payload)

    def subscribe(self, event_name: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        self._subs.setdefault(event_name, []).append(handler)

    # ── waterfall（around-middleware 链）────────────────

    def on_waterfall(self, event_name: str, listener: WaterfallListener) -> None:
        """注册 waterfall 监听器。listener 签名：``async (payload, next) -> payload``。"""
        self._waterfall_subs.setdefault(event_name, []).append(listener)

    async def waterfall(self, event_name: str, initial: Any) -> Any:
        """Around-middleware 分发：listener 链式调用 next()，短路不调 next。"""
        chain = list(self._waterfall_subs.get(event_name, []))

        async def dispatch(idx: int, value: Any) -> Any:
            if idx >= len(chain):
                return value
            listener = chain[idx]

            async def next_fn(v: Any) -> Any:
                return await dispatch(idx + 1, v)

            return await listener(value, next_fn)

        return await dispatch(0, initial)

    # ── serial（串行决策链）────────────────────────────

    def on_serial(self, event_name: str, listener: SerialListener) -> None:
        """注册 serial 监听器。listener 签名：``async (payload) -> payload``。"""
        self._serial_subs.setdefault(event_name, []).append(listener)

    async def serial(self, event_name: str, initial: Any) -> Any:
        """串行分发：每个 listener 收到上一轮的 payload，返回值传给下一个。"""
        value = initial
        for listener in self._serial_subs.get(event_name, []):
            value = await listener(value)
        return value

    # ── drain ───────────────────────────────────────────

    async def drain(self) -> None:
        """等待已发射事件的订阅者处理完毕。

        run 收尾前调用，确保 fire-and-forget 派发的桥接事件（如
        step.completed → journal）先于容器关闭落地。处理过程中新产生的
        任务也会被纳入（收敛到空为止）。
        """
        while self._tasks:
            pending = list(self._tasks)
            await asyncio.gather(*pending, return_exceptions=True)
