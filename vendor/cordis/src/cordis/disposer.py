"""`cordis.disposer` — disposal primitives (Disposer protocol + Effect helper).

This module implements the Python equivalent of TS `Symbol.dispose` and the
`utils.ts` `Effect` types.

Two shapes are accepted:

1. **Single disposer**: a callable returning `None` or an awaitable.
2. **Iterable disposer**: a sync/async iterable yielding one or more disposers.

Disposers run in reverse registration order. Duplicate registrations of the
same callable are deduplicated.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

_LOG_PREFIX = "[cordis]"


class DisposableMixin(Protocol):
    """Objects that implement an async `dispose()` method."""

    async def dispose(self) -> Any:  # pragma: no cover — protocol
        ...


@dataclass
class Disposer:
    """A registered cleanup step with a stable label for diagnostics.

    The `func` may be:

    - a sync callable returning `None` or any awaitable,
    - a coroutine, or
    - a sync / async iterable yielding one or more further disposers.
    """

    func: Callable[[], Any]
    label: str = "disposer"
    dedupe_key: int | None = None
    # Inner-field used so we can dedupe by identity of `func`.
    _seen: set[int] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            self.dedupe_key = id(self.func)
        except TypeError:  # pragma: no cover — not hashable, can't dedupe
            self.dedupe_key = None


async def run_disposer(disp: Disposer) -> None:
    """Run a single `Disposer`, supporting sync / async / iterable results."""
    result = disp.func()
    if inspect.isawaitable(result):
        await result
        return
    # Duck-typed iterable / async-iterable check via `inspect`.
    if inspect.isasyncgen(result) or hasattr(result, "__aiter__"):
        async for _ in result:  # pragma: no cover — async iter of disposers
            pass
        return
    if inspect.isgenerator(result) or hasattr(result, "__iter__"):
        if isinstance(result, (str, bytes)):
            return
        for _ in result:  # pragma: no cover — sync iter of disposers
            pass


@dataclass
class Effect:
    """Represents one or more disposers collected from a single effect call.

    `Effect.of(...)` accepts:

    - a single value (treated as the disposer),
    - an iterable of disposers,
    - or an async iterable.

    `__disposer__` returns a disposer that runs them all in reverse order,
    skipping duplicates by function identity.
    """

    dispose_fns: list[Callable[[], Any]] = field(default_factory=list)

    @classmethod
    def of(cls, value: Any) -> Effect:
        """Coerce `value` into an Effect."""
        if isinstance(value, Effect):
            return value
        if value is None:
            return cls()
        if isinstance(value, (list, tuple)):
            # Each element is one disposer.
            return cls(dispose_fns=list(value))
        return cls(dispose_fns=[_as_func(value)])

    @property
    def __disposer__(self) -> Callable[[], Any]:
        """Return a callable that disposes all registered functions."""
        seen: set[int] = set()

        async def _do_dispose() -> None:
            # Reverse order, dedup by function identity.
            fns = list(reversed(self.dispose_fns))
            for fn in fns:
                key = _safe_id(fn)
                if key in seen:
                    continue
                seen.add(key)
                result = fn()
                if inspect.isawaitable(result):
                    await result

        _do_dispose.__effect__ = self  # type: ignore[attr-defined]
        return _do_dispose


def _as_func(value: Any) -> Callable[[], Any]:
    """Convert `value` into a single-disposer function."""
    if callable(value):
        return value
    # Sentinel for raw values (treat as no-op).
    return lambda v=value: v


def _safe_id(fn: Any) -> int:
    try:
        return id(fn)
    except TypeError:  # pragma: no cover
        return hash(fn)


async def dispose_all(values: Iterable[Callable[[], Any]] | AsyncIterable[Callable[[], Any]]) -> None:
    """Run each value's disposer; await if it returns an awaitable."""
    # Duck-typed async-iterable check (Iterable does not declare __aiter__).
    if inspect.isasyncgen(values) or hasattr(values, "__aiter__"):
        async def _collect() -> None:
            async for fn in values:  # pragma: no cover
                await _run_one(fn)
        await _collect()
        return

    # Iterable path.
    iter_values = values if hasattr(values, "__iter__") else iter(values)  # type: ignore[arg-type]
    for fn in iter_values:  # pragma: no cover
        await _run_one(fn)


async def _run_one(fn: Callable[[], Any]) -> None:
    result = fn()
    if inspect.isawaitable(result):
        await result


__all__ = [
    "DisposableMixin",
    "Disposer",
    "Effect",
    "dispose_all",
    "run_disposer",
]
