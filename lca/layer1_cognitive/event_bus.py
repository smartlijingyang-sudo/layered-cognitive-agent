"""CordisEventBus —— cordis 5 模事件的 typed wrapper。

把 cordis 原生 ``ctx.events.{emit, parallel, serial, bail, waterfall}`` 包装
成 LCA 业务层唯一允许的事件总线，对外仍暴露 ``EventBus`` Protocol（emit /
subscribe / waterfall / serial / drain）。不再保留私有的 SimpleEventBus 字典
实现 —— 任何 LCA 业务代码只能走这条路径。

设计来源：DSH Cordis 5 模分发（emit / parallel / serial / bail / waterfall）。

Public entry points:
- :class:`CordisEventBus` — production wrapper around a booted cordis Context.
- :class:`SimpleEventBus` — back-compat shim for unit tests / legacy defaults
  that construct an EventBus without booting a profile. Implements the same
  five-mode dispatch over its own listener tables; does NOT depend on cordis.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.mechanisms import EventBus

# Waterfall listener: (payload, next_fn) -> payload
WaterfallListener = Callable[[Any, Callable[[Any], Awaitable[Any]]], Awaitable[Any]]
# Serial listener: payload -> payload
SerialListener = Callable[[Any], Awaitable[Any]]
# Parallel listener: payload -> None (fire-and-forget within parallel group)
ParallelListener = Callable[[Any], Awaitable[None]]


def _is_bailed(value: Any) -> bool:
    """True iff value is not None and not False (mirrors cordis ``isBailed``)."""
    return value is not None and value is not False


class CordisEventBus(EventBus):
    """Wrap a booted cordis Context as the LCA EventBus.

    The wrapper never owns subscriptions — they live on the cordis Context,
    which means plugin code can register listeners (``ctx.on(...)``) at
    setup time and the bus will dispatch to them at runtime.
    """

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx
        self._pending: set[asyncio.Task[Any]] = set()

    @property
    def ctx(self) -> Any:
        return self._ctx

    # ── emit（fire-and-forget）──────────────────────────

    def emit(self, event_name: str, payload: dict[str, Any], trace_id: str) -> None:
        envelope = {"event_name": event_name, "payload": payload, "trace_id": trace_id}
        hooks = list(self._ctx.events._hooks.get(event_name, []))
        if not hooks:
            return
        for hook in hooks:
            cb = hook.callback
            try:
                result = cb(envelope)
            except Exception as exc:
                import structlog

                structlog.get_logger("lca.event_bus").warning(
                    "emit_listener_error",
                    event_name=event_name,
                    listener=getattr(cb, "__qualname__", repr(cb)),
                    exc_info=exc,
                )
                continue
            if inspect.isawaitable(result):
                task = asyncio.create_task(_awaitable_to_task(result))
                self._pending.add(task)
                task.add_done_callback(self._pending.discard)

    def subscribe(
        self, event_name: str, handler: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Register a fire-and-forget listener — alias for ``ctx.events.on``."""
        self._ctx.events.on(event_name, handler)

    async def drain(self) -> None:
        """Wait for every fire-and-forget task spawned by ``emit`` to settle."""
        while self._pending:
            pending = list(self._pending)
            await asyncio.gather(*pending, return_exceptions=True)

    # ── waterfall（around-middleware 链）────────────────

    def on_waterfall(self, event_name: str, listener: WaterfallListener) -> None:
        self._ctx.events.on(event_name, listener)

    async def waterfall(self, event_name: str, initial: Any) -> Any:
        """Around-middleware dispatch via ``ctx.events.waterfall``."""
        return await self._ctx.events.waterfall(event_name, initial)

    # ── serial（last-listener-wins）─────────────────────

    def on_serial(self, event_name: str, listener: SerialListener) -> None:
        self._ctx.events.on(event_name, listener)

    async def serial(self, event_name: str, initial: Any) -> Any:
        """Last-listener-wins dispatch via ``ctx.events.serial``."""
        return await self._ctx.events.serial(event_name, initial)

    # ── parallel（cordis 5 模扩展）─────────────────────

    def on_parallel(self, event_name: str, listener: ParallelListener) -> None:
        self._ctx.events.on(event_name, listener)

    async def parallel(self, event_name: str, initial: Any) -> Any:
        """Concurrent dispatch via ``ctx.events.parallel``."""
        return await self._ctx.events.parallel(event_name, initial)

    # ── bail（短路）──────────────────────────────────────

    def on_bail(self, event_name: str, listener: Callable[..., Any]) -> None:
        self._ctx.events.on(event_name, listener)

    async def bail(self, event_name: str, initial: Any) -> Any:
        """Bail-on-first-truthy dispatch via ``ctx.events.bail``."""
        return await self._ctx.events.bail(event_name, initial)


async def _awaitable_to_task(awaitable: Awaitable[Any]) -> Any:
    return await awaitable


def cordis_event_bus(ctx: Any) -> CordisEventBus:
    """Return a :class:`CordisEventBus` wrapping *ctx*."""
    return CordisEventBus(ctx)


# ── Back-compat shim ─────────────────────────────────────────────
#
# Old code paths registered ``SimpleEventBus`` as a default in
# ``lca/layer4_app/defaults.py`` and unit tests construct it directly.
# Both call sites now resolve through this shim, which is a self-
# contained 5-mode dispatch layer that does NOT depend on cordis (so
# unit tests that don't boot a profile keep working). Production
# runtime must use :class:`CordisEventBus` over a booted ctx.


class SimpleEventBus(EventBus):
    """Self-contained EventBus for legacy callers and unit tests.

    Implements the same five-mode dispatch (emit / parallel / serial /
    bail / waterfall) using only stdlib. Listener signatures match the
    cordis conventions:

    * waterfall listener: ``async (payload, nxt) -> payload``
    * serial listener:    ``async (payload) -> payload``
    * parallel listener:  ``async (payload) -> None``
    * bail listener:      ``(payload) -> truthy|None``
    """

    def __init__(self) -> None:
        self._waterfall: dict[str, list[WaterfallListener]] = {}
        self._serial: dict[str, list[SerialListener]] = {}
        self._parallel: dict[str, list[ParallelListener]] = {}
        self._bail: dict[str, list[Callable[..., Any]]] = {}
        self._emit: dict[str, list[Callable[..., Any]]] = {}
        self._pending: set[asyncio.Task[Any]] = set()

    @property
    def ctx(self) -> Any:
        return None

    # ── emit（fire-and-forget）──────────────────────────

    def emit(self, event_name: str, payload: dict[str, Any], trace_id: str) -> None:
        envelope = {"event_name": event_name, "payload": payload, "trace_id": trace_id}
        for cb in list(self._emit.get(event_name, [])):
            try:
                result = cb(envelope)
            except Exception as exc:
                import structlog

                structlog.get_logger("lca.event_bus").warning(
                    "emit_listener_error",
                    event_name=event_name,
                    listener=getattr(cb, "__qualname__", repr(cb)),
                    exc_info=exc,
                )
                continue
            if inspect.isawaitable(result):
                task = asyncio.create_task(_awaitable_to_task(result))
                self._pending.add(task)
                task.add_done_callback(self._pending.discard)

    def subscribe(
        self, event_name: str, handler: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        self._emit.setdefault(event_name, []).append(handler)

    async def drain(self) -> None:
        while self._pending:
            pending = list(self._pending)
            await asyncio.gather(*pending, return_exceptions=True)

    # ── waterfall（around-middleware 链）────────────────

    def on_waterfall(self, event_name: str, listener: WaterfallListener) -> None:
        self._waterfall.setdefault(event_name, []).append(listener)

    async def waterfall(self, event_name: str, initial: Any) -> Any:
        chain = list(self._waterfall.get(event_name, []))

        async def dispatch(idx: int, value: Any) -> Any:
            if idx >= len(chain):
                return value
            listener = chain[idx]

            async def next_fn(v: Any) -> Any:
                return await dispatch(idx + 1, v)

            return await listener(value, next_fn)

        return await dispatch(0, initial)

    # ── serial（last-listener-wins）─────────────────────

    def on_serial(self, event_name: str, listener: SerialListener) -> None:
        self._serial.setdefault(event_name, []).append(listener)

    async def serial(self, event_name: str, initial: Any) -> Any:
        value = initial
        for listener in self._serial.get(event_name, []):
            value = await listener(value)
        return value

    # ── parallel（cordis 5 模扩展）─────────────────────

    def on_parallel(self, event_name: str, listener: ParallelListener) -> None:
        self._parallel.setdefault(event_name, []).append(listener)

    async def parallel(self, event_name: str, initial: Any) -> Any:
        listeners = self._parallel.get(event_name, [])
        if not listeners:
            return initial
        await asyncio.gather(
            *(listener(initial) for listener in listeners),
            return_exceptions=True,
        )
        return initial

    # ── bail（短路）──────────────────────────────────────

    def on_bail(self, event_name: str, listener: Callable[..., Any]) -> None:
        self._bail.setdefault(event_name, []).append(listener)

    async def bail(self, event_name: str, initial: Any) -> Any:
        for cb in self._bail.get(event_name, []):
            result = cb(initial)
            if inspect.isawaitable(result):
                result = await result
            if _is_bailed(result):
                return result
        return None


__all__ = [
    "CordisEventBus",
    "ParallelListener",
    "SerialListener",
    "SimpleEventBus",
    "WaterfallListener",
    "cordis_event_bus",
]
