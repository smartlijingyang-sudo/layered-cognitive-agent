"""``wrap_instrument`` — assembler-mandated phase graph instrumentation (PR-4).

Every runnable attached to an ``ExecutableNode`` must pass through
:func:`wrap_instrument` before the assembler returns the executable
plan. The wrapper closes the spine contract for Layer-3 build-time
validation:

* Push a :class:`SpanContext` for the call
* Emit ``phase_graph.node.start`` before delegation
* Emit ``phase_graph.node.end`` with ``outcome="success"`` on return
* Emit ``phase_graph.node.end`` with ``outcome="failure"`` and
  re-raise on exception; the failure payload carries the structured
  ``exc_type`` / ``exception_message`` / ``traceback_text`` /
  ``cause_chain`` fields (ADR-2026-09-02-i17-stream-align §B) so
  coding-agent tooling can render the failure without re-raising it
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

Emission routing (PR-7.1)
-------------------------
The actual spine emission lives in :mod:`...instrument.events`; when
an ``emit_pipeline`` is installed via
:func:`set_active_pipeline_accessor`, every event goes through
``EmitPipeline.emit(...)`` so all enabled ``FieldProducer`` plugins
contribute their keys to ``EventRecord.payload``. With no pipeline
installed the wrapper falls back to a direct ``EventSpine.append(...)``,
keeping the PR-4 assembler contract intact for pre-boot and unit-test
paths.

``lca.harness`` must not statically import ``lca.plugins`` or
``lca.infrastructure``, so the pipeline is reached duck-typed via the
accessor seam in :mod:`...instrument.accessors` and all spine types
come from :mod:`lca.contracts.observability`.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, overload

from lca.contracts.observability import SpineContext
from lca.contracts.observability.canonical_digest import canonical_digest
from lca.harness.declarative.compile.instrument.accessors import (
    _resolve_spine,
    resolve_active_pipeline,
    resolve_active_spine,
    set_active_pipeline_accessor,
    set_active_spine_accessor,
)
from lca.harness.declarative.compile.instrument.events import (
    _emit_spine_direct,
    _exception_payload,
    _safe_append,
)

WRAP_INSTRUMENTED_ATTR = "__lca_instrumented__"
ASSEMBLER_PROVENANCE = "assembler"
DEFAULT_START_EXECUTION_POINT = "phase_graph.node.start"
DEFAULT_END_EXECUTION_POINT = "phase_graph.node.end"


_F = TypeVar("_F", bound=Callable[..., Any])


def _fingerprint_value(value: Any) -> str:
    """Stable, short fingerprint of a return value for the ``.end`` payload."""
    try:
        rendered = repr(value)
    except Exception as exc:
        rendered = f"<unreprable: {exc!r}>"
    return canonical_digest(rendered, length=16)


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
        except BaseException as exc:
            _safe_append(
                spine=spine,
                execution_point=execution_point_end,
                channel="error",
                payload={"return_value_fingerprint": None},
                outcome="failure",
                span=span,
                exc=exc,
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
        except BaseException as exc:
            _safe_append(
                spine=spine,
                execution_point=execution_point_end,
                channel="error",
                payload={"return_value_fingerprint": None},
                outcome="failure",
                span=span,
                exc=exc,
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


# Split-module back-compat re-exports: consumers predate the split and
# import these helpers from ``wrap`` directly.
__all__ = [
    "ASSEMBLER_PROVENANCE",
    "DEFAULT_END_EXECUTION_POINT",
    "DEFAULT_START_EXECUTION_POINT",
    "WRAP_INSTRUMENTED_ATTR",
    "InstrumentedPhaseExecutor",
    "_emit_spine_direct",
    "_exception_payload",
    "_safe_append",
    "resolve_active_pipeline",
    "resolve_active_spine",
    "set_active_pipeline_accessor",
    "set_active_spine_accessor",
    "wrap_executor",
    "wrap_instrument",
]
