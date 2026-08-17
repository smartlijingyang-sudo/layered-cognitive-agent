"""Timer plugin — ``timer`` service with fiber-owned timers (Cordis mirror).

Mirrors DSH ``vendor/timer``. All timers belong to the plugin's fiber: they
are registered as effects and cleared on unload. ``timeout`` / ``interval``
accept either a callback (returns a disposer) or a bare delay (returns an
awaitable / async iterator of ticks).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from lca.layer0_infra.plugin.kernel._context import PluginContext
from lca.layer0_infra.plugin.kernel._service import Service


class TimerService(Service):
    """Fiber-scoped timers. ``ctx.timeout`` / ``ctx.interval`` helpers."""

    name = "timer"

    def __init__(self, ctx: PluginContext, config: Any = None) -> None:
        super().__init__(ctx, config)

    def timeout(self, delay: float, callback: Callable[[], Any] | None = None) -> Any:
        """Run *callback* once after *delay* seconds.

        With a callback: returns a disposer that cancels the pending timer.
        Without: returns an awaitable that resolves after *delay*, rejected
        if the fiber is disposed first.
        """
        if callback is not None:
            holder: list[asyncio.TimerHandle] = []

            def setup_cb() -> Callable[[], None]:
                loop = asyncio.get_event_loop()
                handle = loop.call_later(delay, callback)
                holder.append(handle)

                def cleanup() -> None:
                    if holder and not holder[0].cancelled():
                        holder[0].cancel()

                return cleanup

            self.ctx.effect(setup_cb, "ctx.timeout()")
            return holder[0].cancel if holder else lambda: None

        loop = asyncio.get_event_loop()
        future: asyncio.Future[None] = loop.create_future()

        def _fire() -> None:
            if not future.done():
                future.set_result(None)

        def setup_future() -> Callable[[], None]:
            handle = loop.call_later(delay, _fire)

            def cleanup() -> None:
                if not handle.cancelled():
                    handle.cancel()
                if not future.done():
                    future.cancel()

            return cleanup

        self.ctx.effect(setup_future, "ctx.timeout()")
        return future

    def interval(self, delay: float, callback: Callable[[], Any] | None = None) -> Any:
        """Run *callback* every *delay* seconds.

        With a callback: returns a disposer that clears the interval.
        Without: returns an async iterator of ticks.
        """
        if callback is not None:
            holder: list[asyncio.TimerHandle] = []
            cancelled = False

            def setup() -> Callable[[], None]:
                loop = asyncio.get_event_loop()

                def _tick() -> None:
                    if cancelled:
                        return
                    callback()
                    holder[0] = loop.call_later(delay, _tick)

                handle = loop.call_later(delay, _tick)
                holder.append(handle)

                def cleanup() -> None:
                    nonlocal cancelled
                    cancelled = True
                    if holder and not holder[0].cancelled():
                        holder[0].cancel()

                return cleanup

            self.ctx.effect(setup, "ctx.interval()")
            return holder[0].cancel if holder else lambda: None

        return _Ticks(delay, self.ctx)

    def debounce(self, callback: Callable[..., Any], delay: float) -> Callable[..., None]:
        """Return a debounced wrapper whose timer is fiber-owned."""
        holder: list[asyncio.TimerHandle | None] = [None]

        def cancel() -> None:
            if holder[0] is not None and not holder[0].cancelled():
                holder[0].cancel()
            holder[0] = None

        self.ctx.effect(lambda: cancel, "ctx.debounce()")

        def wrapper(*args: Any, **kwargs: Any) -> None:
            cancel()
            loop = asyncio.get_event_loop()
            holder[0] = loop.call_later(delay, callback, *args)

        wrapper.dispose = cancel  # type: ignore[attr-defined]
        return wrapper

    def throttle(self, callback: Callable[..., Any], delay: float) -> Callable[..., None]:
        """Return a throttled wrapper (at most one pending run)."""
        last_run = 0.0
        pending: list[asyncio.TimerHandle | None] = [None]

        def cancel() -> None:
            if pending[0] is not None and not pending[0].cancelled():
                pending[0].cancel()
            pending[0] = None

        self.ctx.effect(lambda: cancel, "ctx.throttle()")

        def wrapper(*args: Any, **kwargs: Any) -> None:
            nonlocal last_run, pending
            now = time.monotonic()
            if pending[0] is not None:
                return
            if now - last_run >= delay:
                last_run = now
                callback(*args)
                return
            remaining = delay - (now - last_run)
            loop = asyncio.get_event_loop()
            pending[0] = loop.call_later(remaining, lambda: callback(*args))

        wrapper.dispose = cancel  # type: ignore[attr-defined]
        return wrapper


class _Ticks:
    """Async iterator of interval ticks; disposal via ``ctx.effect``."""

    def __init__(self, delay: float, ctx: PluginContext) -> None:
        self._delay = delay
        self._ctx = ctx
        self._queue: asyncio.Queue[None] = asyncio.Queue()
        self._stopped = False
        self._task: asyncio.Task[None] | None = None
        self._started = False

    def __aiter__(self) -> _Ticks:
        self._start()
        return self

    def _start(self) -> None:
        if self._started:
            return
        self._started = True
        loop = asyncio.get_event_loop()

        async def _run() -> None:
            while not self._stopped:
                await asyncio.sleep(self._delay)
                if self._stopped:
                    break
                self._queue.put_nowait(None)

        self._task = loop.create_task(_run())
        self._ctx.effect(lambda: self._close(), "ctx.interval()")

    def _close(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def __anext__(self) -> None:
        if self._stopped and self._queue.empty():
            raise StopAsyncIteration
        await self._queue.get()
        return None


# Class-plugin export: Loader constructs ``TimerService(ctx, config)``.
name = "timer"
provides = "timer"
apply = TimerService
