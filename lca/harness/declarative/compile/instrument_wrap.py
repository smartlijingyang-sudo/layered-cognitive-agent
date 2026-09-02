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
When an ``emit_pipeline`` is installed via
:func:`set_active_pipeline_accessor`, every event goes through
``EmitPipeline.emit(...)`` so all enabled ``FieldProducer`` plugins
(signature / source / spantree / context / runtime) contribute their
keys to ``EventRecord.payload``. With no pipeline installed the wrapper
falls back to a direct ``EventSpine.append(...)``, keeping the PR-4
assembler contract intact for pre-boot and unit-test paths.

``lca.harness`` must not statically import ``lca.plugins``, so the
pipeline is reached duck-typed via the accessor rather than by
importing ``EmitPipeline``.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import logging
import traceback
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, overload

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


def _is_i17_violation(exc: BaseException) -> bool:
    """Duck-typed check for ``I17Violation`` without a static import.

    ``lca.harness`` must not statically import ``lca.plugins``. The
    I17 class lives in :mod:`lca.plugins.observability.spine.emit_pipeline`
    and is identifiable by its fully-qualified name. This lets the
    wrapper route I17 failures to a dedicated traceback-emitting path
    (the silent-swallow bug from ADR-2026-09-02-i17-traceback §A) while
    keeping the assembler import graph unchanged.
    """
    cls = type(exc)
    return (
        cls.__module__ == "lca.plugins.observability.spine.emit_pipeline"
        and cls.__name__ == "I17Violation"
    )


_F = TypeVar("_F", bound=Callable[..., Any])

# Process-local active spine accessors live alongside the spine reflector
# plugins. Importing them directly would create a cross-layer cycle
# (assembler → observability plugin → assembler). Instead we expose a
# pluggable accessor that the spine plugins can register against and
# fall back to ``None`` in unit tests.

_active_spine_getter: Callable[[], EventSpine | None] | None = None
_active_pipeline_getter: Callable[[], Any] | None = None


def set_active_spine_accessor(
    getter: Callable[[], EventSpine | None] | None,
) -> Callable[[], EventSpine | None] | None:
    """Install a process-local spine accessor used by :func:`wrap_instrument`.

    Returns the previous accessor so callers can restore it (typically
    tests using a ``monkeypatch`` style scope).
    """
    global _active_spine_getter
    previous = _active_spine_getter
    _active_spine_getter = getter
    return previous


def set_active_pipeline_accessor(
    getter: Callable[[], Any] | None,
) -> Callable[[], Any] | None:
    """Install a process-local EmitPipeline accessor for :func:`wrap_instrument`.

    When a pipeline is installed, ``wrap_instrument`` routes every
    emission through ``EmitPipeline.emit(...)`` so enabled
    ``FieldProducer`` plugins contribute their keys to
    ``EventRecord.payload``. With no pipeline installed, the wrapper
    falls back to the direct ``EventSpine.append`` path so PR-4
    assembler contracts still hold under unit tests.

    Returns the previous accessor so callers can restore it.
    """
    global _active_pipeline_getter
    previous = _active_pipeline_getter
    _active_pipeline_getter = getter
    return previous


def _resolve_spine() -> EventSpine | None:
    if _active_spine_getter is None:
        return None
    try:
        return _active_spine_getter()
    except Exception as exc:  # pragma: no cover — defensive only
        log.warning("wrap_instrument: spine accessor raised %r", exc)
        return None


def _resolve_pipeline() -> Any:
    """Return the active ``EmitPipeline`` (structural Protocol), or ``None``.

    The protocol is structural: we never import :class:`EmitPipeline`
    here because ``lca.harness`` must not statically import
    ``lca.plugins`` (plugin tree is an optional boot-time layer). The
    pipeline accessor is registered by the boot path via
    :func:`set_active_pipeline_accessor` and the wrapper calls the
    duck-typed ``emit(...)`` method.
    """
    if _active_pipeline_getter is None:
        return None
    try:
        return _active_pipeline_getter()
    except Exception as exc:  # pragma: no cover — defensive only
        log.warning("wrap_instrument: pipeline accessor raised %r", exc)
        return None


def resolve_active_pipeline() -> Any:
    """Return the installed ``emit_pipeline`` or ``None`` when unwired.

    Public counterpart of :func:`_resolve_pipeline` for the
    ``ctx_effect`` / ``ctx_intercept`` wrap plugins, which must resolve
    the same pipeline through the same seam rather than reach into this
    module's private helpers or install a second accessor.
    """
    return _resolve_pipeline()


def resolve_active_spine() -> EventSpine | None:
    """Return the installed ``EventSpine`` or ``None`` when unwired.

    Public counterpart of :func:`_resolve_spine`; see
    :func:`resolve_active_pipeline` for why the wrap plugins need it.
    """
    return _resolve_spine()


def _fingerprint_value(value: Any) -> str:
    """Stable, short fingerprint of a return value for the ``.end`` payload."""
    try:
        rendered = repr(value)
    except Exception as exc:
        rendered = f"<unreprable: {exc!r}>"
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


# ``_TRACEBACK_CAPPED_BYTES`` mirrors ``_publish_i17_rejection`` (ADR-0165.1 §96).
# 4 KiB is enough to keep the most recent frames of a typical agent call while
# keeping the per-event jsonl cost bounded.
_TRACEBACK_CAPPED_BYTES = 4096


def _exception_payload(exc: BaseException) -> dict[str, Any]:
    """Structured failure fields (ADR-2026-09-02-i17-stream-align §B).

    The wrap layer must propagate the original exception text into the
    journal payload so a coding agent (and ``lca-ops explain`` /
    ``doctor``) can recover the traceback from disk without re-raising
    the exception. Field names mirror the public contract agreed on
    2026-09-02:

    - ``exc_type``           — ``type(exc).__qualname__``
    - ``exception_message``  — ``str(exc)`` (may be empty)
    - ``traceback_text``     — formatted chain, capped to 4 KiB
    - ``cause_chain``        — tuple of qualnames for ``__cause__`` /
      ``__context__`` (one level deep, deterministic order)

    The historic ``exception_class`` / ``reason`` fields are also kept
    so existing readers (e.g. ``spine.producer.failure`` projector,
    ADR-0165.1 §96 ``_publish_i17_rejection``) continue to function
    unchanged.
    """
    exc_type = type(exc).__qualname__
    exc_message = str(exc)
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    tb_capped = tb_text.encode("utf-8", errors="replace")[:_TRACEBACK_CAPPED_BYTES]
    cause_chain: list[str] = []
    for link in (exc.__cause__, exc.__context__):
        if link is None or link is exc:
            continue
        cause_chain.append(type(link).__qualname__)
    return {
        "exc_type": exc_type,
        "exception_class": exc_type,  # legacy alias — see docstring
        "exception_message": exc_message,
        "reason": exc_message,  # legacy alias — see docstring
        "traceback_text": tb_capped.decode("utf-8", errors="ignore"),
        "cause_chain": cause_chain,
    }


def _safe_append(
    *,
    spine: EventSpine | None,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any],
    outcome: OutcomeT | None,
    span: SpanContext | None,
    exc: BaseException | None = None,
) -> None:
    """Emit a spine event without letting a broken helper block the caller.

    When a process-local EmitPipeline accessor is installed (PR-7.1),
    the emission is routed through it so enabled ``FieldProducer``
    plugins may merge their keys into the payload before the
    ``EventRecord`` is sealed. When no pipeline is installed this
    function falls back to the direct ``EventSpine.append`` path so
    PR-4 assembler contracts still hold under unit tests.

    ``exc`` carries a ``BaseException`` captured by the wrap layer at
    the call site. When provided it is merged into the payload as the
    structured failure fields documented in :func:`_exception_payload`,
    so a channel="error" event always carries enough information to
    render the traceback without re-raising.
    """
    if exc is not None:
        # Caller payload wins on conflict (the caller may override
        # ``exception_message`` with a domain-specific phrasing), so we
        # merge exc first and then apply caller payload on top.
        payload = {**_exception_payload(exc), **payload}
    pipeline = _resolve_pipeline()
    if pipeline is not None and spine is not None:
        try:
            pipeline.emit(
                execution_point=execution_point,
                channel=channel,
                span_ctx=span,
                caller_payload=payload,
                spine=spine,
                outcome=outcome,
            )
        except ValueError as exc:
            log.warning(
                "wrap_instrument: drop invalid event ep=%s err=%s",
                execution_point,
                exc,
                exc_info=True,
            )
        except Exception as exc:
            if _is_i17_violation(exc):
                # ADR-2026-09-02-i17-traceback §D1: I17 failures MUST
                # surface their traceback (the original code swallowed
                # them as a generic ``log.warning`` without
                # ``exc_info=True``). The assembler wraps every phase,
                # so losing the traceback here loses the entire
                # evidence trail for any *.start rejection.
                _publish_i17_rejection(
                    spine=spine,
                    span=span,
                    attempted_ep=execution_point,
                    exc=exc,
                    channel=channel,
                )
                log.error(
                    "wrap_instrument: I17 rejected ep=%s reason=%s",
                    execution_point,
                    exc,
                    exc_info=True,
                )
            else:
                log.warning(
                    "wrap_instrument: pipeline emit failed ep=%s err=%s",
                    execution_point,
                    exc,
                    exc_info=True,
                )
        return
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
            exc_info=True,
        )
    except Exception as exc:
        # FD-1 sink failures are supposed to propagate, but only to the
        # caller that triggered the emit. The wrap site is not a
        # business surface; contain it so a broken spine never aborts
        # the wrapped runnable mid-execution.
        if _is_i17_violation(exc):
            _publish_i17_rejection(
                spine=spine,
                span=span,
                attempted_ep=execution_point,
                exc=exc,
                channel=channel,
            )
            log.error(
                "wrap_instrument: I17 rejected ep=%s reason=%s",
                execution_point,
                exc,
                exc_info=True,
            )
        else:
            log.warning(
                "wrap_instrument: spine emit failed ep=%s err=%s",
                execution_point,
                exc,
                exc_info=True,
            )


def _publish_i17_rejection(
    *,
    spine: EventSpine,
    span: SpanContext | None,
    attempted_ep: str,
    exc: BaseException,
    channel: Channel,
) -> None:
    """Emit one ``spine.i17.rejected`` journal event with the original traceback.

    Mirrors ``EmitPipeline``'s sidecar style so the rejection is
    recoverable from the run directory (rather than only from
    stderr). Falls back to a ``log.warning`` when the spine itself
    rejects the publication — we never want reject-noticing to
    mask the original I17.
    """
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    capped = tb_text.encode("utf-8", errors="replace")[:4096]
    try:
        spine.append(
            execution_point="spine.i17.rejected",
            channel="error",
            caller_payload={
                "attempted_execution_point": attempted_ep,
                "exception_class": type(exc).__qualname__,
                "reason": str(exc),
                "traceback_text": capped.decode("utf-8", errors="ignore"),
                "span_id": getattr(span, "span_id", None),
                "outer_channel": str(channel),
            },
            outcome="failure",
            span_ctx=span,
        )
    except Exception as publish_exc:
        log.warning(
            "wrap_instrument: spine.i17.rejected publication failed "
            "err=%s; I17 traceback still on stderr",
            publish_exc,
            exc_info=True,
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


__all__ = [
    "ASSEMBLER_PROVENANCE",
    "DEFAULT_END_EXECUTION_POINT",
    "DEFAULT_START_EXECUTION_POINT",
    "WRAP_INSTRUMENTED_ATTR",
    "InstrumentedPhaseExecutor",
    "resolve_active_pipeline",
    "resolve_active_spine",
    "set_active_pipeline_accessor",
    "set_active_spine_accessor",
    "wrap_executor",
    "wrap_instrument",
]
