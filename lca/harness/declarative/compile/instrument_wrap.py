"""``wrap_instrument`` — assembler-mandated phase graph instrumentation (PR-4).

Every runnable attached to an ``ExecutableNode`` must pass through
:func:`wrap_instrument` before the assembler returns the executable
plan. The wrapper closes the spine contract for Layer-3 build-time
validation:

* Push a :class:`SpanContext` for the call
* Emit ``phase_graph.node.start`` before delegation
* Emit ``phase_graph.node.end`` with ``outcome="success"`` on return
* Emit ``phase_graph.node.end`` with ``outcome="failure"`` and
  re-raise on exception
* Stamp the wrapper with ``__lca_instrumented__`` and
  ``wrap_provenance = "assembler"`` so downstream catalogs and the
  build-time check can prove the node was wrapped here

The wrapper is **safe to compose**:

* ``functools.wraps`` preserves the original signature, name, docstring
  and attributes (including ``__wrapped__`` for introspection)
* sync and async callables are both supported (PhaseExecutor's
  ``execute`` is async, but business-side helpers may be sync)
* the emission path tolerates a missing active spine — the assembler
  runs in unit tests where no spine is wired, and instrumentation
  must not change observable behaviour in that mode
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Optional, TypeVar, overload

from lca.infrastructure.observability.spine.context import (
    SpanContext,
    SpineContext,
)
from lca.infrastructure.observability.spine.event_record import Channel
from lca.infrastructure.observability.spine.event_record import Outcome as OutcomeT
from lca.infrastructure.observability.spine.event_spine import EventSpine

log = logging.getLogger(__name__)

WRAP_INSTRUMENTED_ATTR = "__lca_instrumented__"
ASSEMBLER_PROVENANCE = "assembler"
DEFAULT_START_EXECUTION_POINT = "phase_graph.node.start"
DEFAULT_END_EXECUTION_POINT = "phase_graph.node.end"

_F = TypeVar("_F", bound=Callable[..., Any])

# Process-local active spine accessors live alongside the spine reflector
# plugins. Importing them directly would create a cross-layer cycle
# (assembler → observability plugin → assembler). Instead we expose a
# pluggable accessor that the spine plugins can register against and
# fall back to ``None`` in unit tests.

_active_spine_getter: Callable[[], EventSpine | None] | None = None


def set_active_spine_accessor(
    getter: Callable[[], EventSpine | None] | None,
) -> Optional[Callable[[], Optional[EventSpine]]]:
    """Install a process-local spine accessor used by :func:`wrap_instrument`.

    Returns the previous accessor so callers can restore it (typically
    tests using a ``monkeypatch`` style scope).
    """
    global _active_spine_getter
    previous = _active_spine_getter
    _active_spine_getter = getter
    return previous


def _resolve_spine() -> EventSpine | None:
    if _active_spine_getter is None:
        return None
    try:
        return _active_spine_getter()
    except Exception as exc:  # pragma: no cover — defensive only
        log.warning("wrap_instrument: spine accessor raised %r", exc)
        return None


def _fingerprint_value(value: Any) -> str:
    """Stable, short fingerprint of a return value for the ``.end`` payload."""
    try:
        rendered = repr(value)
    except Exception as exc:
        rendered = f"<unreprable: {exc!r}>"
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def _safe_append(
    *,
    spine: EventSpine | None,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any],
    outcome: OutcomeT | None,
    span: SpanContext | None,
) -> None:
    """Emit a spine event without letting a broken helper block the caller."""
    if spine is None:
        return
    try:
        spine.append(
            execution_point=execution_point,
            channel=channel,
            caller_payload=payload,
            outcome=outcome,
            span_ctx=span,
        )
    except ValueError as exc:
        # EventRecord post-init validation failure (malformed payload).
        log.warning(
            "wrap_instrument: drop invalid event ep=%s err=%s",
            execution_point,
            exc,
        )
    except Exception as exc:
        # FD-1 sink failures are supposed to propagate, but only to the
        # caller that triggered the emit. The wrap site is not a
        # business surface; contain it so a broken spine never aborts
        # the wrapped runnable mid-execution.
        log.warning(
            "wrap_instrument: spine emit failed ep=%s err=%s",
            execution_point,
            exc,
        )


def _sync_wrapper(
    fn: Callable[..., Any],
    *,
    execution_point_start: str,
    execution_point_end: str,
) -> Callable[..., Any]:
    @functools.wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        span = SpineContext.push_span(execution_point_start)
        spine = _resolve_spine()
        _safe_append(
            spine=spine,
            execution_point=execution_point_start,
            channel="control",
            payload={"args_count": len(args), "kwargs_count": len(kwargs)},
            outcome=None,
            span=span,
        )
        try:
            result = fn(*args, **kwargs)
        except BaseException:
            _safe_append(
                spine=spine,
                execution_point=execution_point_end,
                channel="error",
                payload={"return_value_fingerprint": None},
                outcome="failure",
                span=span,
            )
            SpineContext.pop_span(execution_point_start)
            raise
        _safe_append(
            spine=spine,
            execution_point=execution_point_end,
            channel="control",
            payload={"return_value_fingerprint": _fingerprint_value(result)},
            outcome="success",
            span=span,
        )
        SpineContext.pop_span(execution_point_start)
        return result

    return wrapped


async def _invoke(fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Call ``fn`` whether it is sync or async, returning the awaitable if async."""
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _async_wrapper(
    fn: Callable[..., Awaitable[Any]],
    *,
    execution_point_start: str,
    execution_point_end: str,
) -> Callable[..., Awaitable[Any]]:
    @functools.wraps(fn)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        span = SpineContext.push_span(execution_point_start)
        spine = _resolve_spine()
        _safe_append(
            spine=spine,
            execution_point=execution_point_start,
            channel="control",
            payload={"args_count": len(args), "kwargs_count": len(kwargs)},
            outcome=None,
            span=span,
        )
        try:
            result = await _invoke(fn, args, kwargs)
        except BaseException:
            _safe_append(
                spine=spine,
                execution_point=execution_point_end,
                channel="error",
                payload={"return_value_fingerprint": None},
                outcome="failure",
                span=span,
            )
            SpineContext.pop_span(execution_point_start)
            raise
        _safe_append(
            spine=spine,
            execution_point=execution_point_end,
            channel="control",
            payload={"return_value_fingerprint": _fingerprint_value(result)},
            outcome="success",
            span=span,
        )
        SpineContext.pop_span(execution_point_start)
        return result

    return wrapped


@overload
def wrap_instrument(
    fn: Callable[..., Awaitable[Any]],
    *,
    node_id: str | None = None,
    execution_point: str | None = None,
    execution_point_start: str | None = None,
    execution_point_end: str | None = None,
) -> Callable[..., Awaitable[Any]]: ...


@overload
def wrap_instrument(
    fn: Callable[..., Any],
    *,
    node_id: str | None = None,
    execution_point: str | None = None,
    execution_point_start: str | None = None,
    execution_point_end: str | None = None,
) -> Callable[..., Any]: ...


def wrap_instrument(
    fn: _F,
    *,
    node_id: str | None = None,
    execution_point: str | None = None,
    execution_point_start: str | None = None,
    execution_point_end: str | None = None,
) -> _F:
    """Wrap ``fn`` so every call emits phase-graph instrumentation events.

    Parameters
    ----------
    fn:
        Callable to wrap. Supports both sync and async callables.
    node_id:
        Optional identifier used as the default ``execution_point``
        suffix and stamped on the wrapper. Today ``node_id`` is purely
        advisory — the event schema is still closed — but call sites
        that already carry a node identifier (assembler, Layer-3
        checks) can pass it for forward compatibility.
    execution_point:
        Convenience override that sets both ``start`` and ``end`` to the
        same execution point. Useful for non-phase-graph instrumentation.
    execution_point_start, execution_point_end:
        Override the default ``phase_graph.node.start`` /
        ``phase_graph.node.end`` execution points. ``start`` and
        ``end`` are independent so call sites that need a different
        closing point (e.g. failure-only sinks) can declare it.

    Returns
    -------
    Callable
        A wrapper carrying the original signature plus the
        ``__lca_instrumented__`` and ``wrap_provenance`` markers.
    """
    start = execution_point or execution_point_start or DEFAULT_START_EXECUTION_POINT
    end = execution_point or execution_point_end or DEFAULT_END_EXECUTION_POINT

    if asyncio.iscoroutinefunction(fn):
        wrapper: Callable[..., Any] = _async_wrapper(
            fn,
            execution_point_start=start,
            execution_point_end=end,
        )
    else:
        wrapper = _sync_wrapper(
            fn,
            execution_point_start=start,
            execution_point_end=end,
        )

    # functools.wraps already attaches ``__wrapped__``; repeat it for
    # code paths where the callable happens to be a builtin that
    # functools.wraps could not annotate.
    wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
    wrapper.__lca_instrumented__ = True  # type: ignore[attr-defined]
    wrapper.wrap_provenance = ASSEMBLER_PROVENANCE  # type: ignore[attr-defined]
    if node_id is not None:
        wrapper.wrap_node_id = node_id  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


class InstrumentedPhaseExecutor:
    """Adapter that preserves a PhaseExecutor's protocol surface after wrapping.

    :func:`wrap_instrument` operates on plain callables, but the
    assembler hands out objects that the runtime calls as
    ``executor.execute(context, input)``. ``InstrumentedPhaseExecutor``
    delegates the public ``execute`` attribute to a wrapped function
    while forwarding every other attribute to the underlying executor.
    """

    __slots__ = ("_executor", "_wrapped_execute")

    def __init__(self, executor: Any, wrapped_execute: Callable[..., Any]) -> None:
        self._executor = executor
        self._wrapped_execute = wrapped_execute

    @property
    def execute(self) -> Callable[..., Any]:
        """Return the wrapped execute callable carrying instrument markers."""
        return self._wrapped_execute

    def __getattr__(self, name: str) -> Any:
        return getattr(self._executor, name)

    def __repr__(self) -> str:
        return f"<InstrumentedPhaseExecutor wrapping {self._executor!r}>"


def wrap_executor(executor: Any) -> Any:
    """Wrap a PhaseExecutor so its ``.execute`` carries instrument markers.

    The returned object keeps the executor's protocol surface so callers
    continue to invoke ``executor.execute(context, input)``. The
    underlying ``.execute`` callable is the only thing instrumented —
    delegating every other attribute preserves identity-sensitive
    checks (e.g. ``isinstance`` against test doubles).
    """
    execute_callable = getattr(executor, "execute", None)
    if not callable(execute_callable):
        raise TypeError("wrap_executor requires an object with a callable 'execute' attribute")
    wrapped_execute = wrap_instrument(execute_callable)
    return InstrumentedPhaseExecutor(executor, wrapped_execute)


__all__ = [
    "ASSEMBLER_PROVENANCE",
    "DEFAULT_END_EXECUTION_POINT",
    "DEFAULT_START_EXECUTION_POINT",
    "WRAP_INSTRUMENTED_ATTR",
    "InstrumentedPhaseExecutor",
    "set_active_spine_accessor",
    "wrap_executor",
    "wrap_instrument",
]
