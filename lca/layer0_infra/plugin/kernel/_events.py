"""EventBus — 5 dispatch modes with lifecycle ownership.

Independent subsystem: owns listeners, dispatches events.
No dependency on PluginHost or PluginContext.
"""

from __future__ import annotations

import asyncio
import inspect
import itertools
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lca.layer0_infra.plugin.kernel._types import Listener

# ExceptionGroup is builtin in 3.11+; fallback for 3.10
if sys.version_info >= (3, 11):
    _ExceptionGroup = ExceptionGroup  # noqa: F821
else:

    class _ExceptionGroup(Exception):  # noqa: N818
        def __init__(self, message: str, exceptions: list[BaseException]) -> None:
            super().__init__(message)
            self.exceptions = exceptions


@dataclass(frozen=True)
class _ListenerRecord:
    token: int
    owner_id: str
    callback: Listener
    prepend: bool = False
    global_: bool = False


class EventBus:
    """5-mode event bus (Cordis EventsService equivalent)."""

    def __init__(self) -> None:
        self._events: dict[str, list[_ListenerRecord]] = defaultdict(list)
        self._counter = itertools.count(1)

    def on(
        self,
        owner_id: str,
        event: str,
        callback: Listener,
        *,
        prepend: bool = False,
        global_: bool = False,
    ) -> tuple[str, int]:
        token = next(self._counter)
        record = _ListenerRecord(token, owner_id, callback, prepend, global_)
        if prepend:
            self._events[event].insert(0, record)
        else:
            self._events[event].append(record)
        return event, token

    def off(self, token: tuple[str, int]) -> bool:
        event, target = token
        listeners = self._events.get(event, [])
        for index, record in enumerate(listeners):
            if record.token == target:
                listeners.pop(index)
                if not listeners:
                    self._events.pop(event, None)
                return True
        return False

    def remove_all_for(self, owner_id: str) -> None:
        for event in list(self._events):
            self._events[event] = [r for r in self._events[event] if r.owner_id != owner_id]
            if not self._events[event]:
                self._events.pop(event)

    def _resolve(
        self,
        event: str,
        filter_fn: Callable[[_ListenerRecord], bool] | None = None,
    ) -> list[Listener]:
        return [
            h.callback
            for h in self._events.get(event, [])
            if h.global_ or not filter_fn or filter_fn(h)
        ]

    # ── 5 dispatch modes ──────────────────────────────────

    async def emit(self, event: str, *args: Any) -> None:
        for cb in self._resolve(event):
            cb(*args)

    async def parallel(self, event: str, *args: Any) -> None:
        cbs = self._resolve(event)
        if not cbs:
            return
        results = await asyncio.gather(*(cb(*args) for cb in cbs), return_exceptions=True)
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            raise _ExceptionGroup("parallel dispatch errors", errors)

    async def serial(self, event: str, *args: Any) -> Any:
        for cb in self._resolve(event):
            result = cb(*args)
            if inspect.isawaitable(result):
                result = await result
            if _bailed(result):
                return result
        return None

    def bail(self, event: str, *args: Any) -> Any:
        for cb in self._resolve(event):
            result = cb(*args)
            if _bailed(result):
                return result
        return None

    async def waterfall(self, event: str, *args: Any, terminal: Callable[[], Any]) -> Any:
        cbs = self._resolve(event)

        def next_step(i: int = 0) -> Any:
            if i >= len(cbs):
                return terminal()
            return cbs[i](*args, lambda i=i: next_step(i + 1))

        result = next_step()
        if inspect.isawaitable(result):
            return await result
        return result


def _bailed(value: Any) -> bool:
    return value is not None and value is not False
