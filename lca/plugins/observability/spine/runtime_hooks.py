"""``ctx_effect`` / ``ctx_intercept`` wrap kinds — both feed ``emit_pipeline``.

ADR-0165.1 §7.6.4 splits spine weaving into three *wrap kinds*. This
module owns the two that are not the phase-graph assembler:

===================  ====================================================
Wrap kind            What it instruments
===================  ====================================================
``ctx_effect``       Context lifecycle. Emits one event when the hook is
                     installed and one when the owning ``cordis``
                     context disposes (the disposer is handed to
                     ``ctx.effect`` so the kernel owns teardown).
``ctx_intercept``    A named attribute on a host object/module. The
                     original callable is replaced with a wrapper that
                     brackets the call with ``.start`` / ``.end`` events;
                     the un-patch is handed to ``ctx.effect``.
===================  ====================================================

The third kind (``assembler``) lives in
:mod:`lca.harness.declarative.compile.instrument_wrap` and is already
routed through the pipeline by :func:`~lca.harness.declarative.compile.instrument_wrap.wrap_instrument`.
Plugin Manifests for all three wrap kinds live under
:mod:`lca.plugins.observability.spine.wraps`.

Single emission seam
--------------------
Every kind resolves the process-local spine accessor installed by
:func:`~lca.harness.declarative.compile.instrument_wrap.set_active_spine_accessor`.
Production runs with a Session SSOT hook active; ``EmitPipeline`` is
hook-less test surface only (ADR-0194 P2-07).

Why ``ctx.intercept`` is a monkeypatch and not a cordis primitive
----------------------------------------------------------------
``cordis.Context`` exposes ``effect(dispose, *, label=...)`` but has no
method-interception primitive — ``Context.intercept`` is an injection
*config map*, not a wrap API. The ``ctx_intercept`` kind is therefore
implemented as a scoped ``setattr`` swap whose undo is registered via
``ctx.effect``, which keeps disposal inside the kernel's existing
ownership model instead of inventing a parallel teardown mechanism.

Failure containment
-------------------
Emission never propagates out of a hook: a broken pipeline, sink or
producer must not abort the intercepted business call. Exceptions raised
by the *wrapped callable itself* always propagate after the failure
event is emitted.
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any

from lca.harness.declarative.compile.instrument.wrap import (
    _emit_spine_direct,
    set_active_spine_accessor,
)
from lca.infrastructure.observability.spine.context.context import SpineContext
from lca.infrastructure.observability.spine.event.record import Channel
from lca.infrastructure.observability.spine.event.record import Outcome as OutcomeT
from lca.infrastructure.observability.spine.event.spine import EventSpine

log = logging.getLogger(__name__)

# Provenance markers mirroring ``ASSEMBLER_PROVENANCE`` so a catalog can
# attribute any wrapper to the kind that installed it.
CTX_EFFECT_PROVENANCE = "ctx_effect"
CTX_INTERCEPT_PROVENANCE = "ctx_intercept"

WRAP_INSTRUMENTED_ATTR = "__lca_instrumented__"


# ── accessor readback ────────────────────────────────────────────────


def _read_spine_accessor() -> Callable[[], EventSpine | None] | None:
    """Return the installed ``EventSpine`` accessor without changing it."""
    current = set_active_spine_accessor(None)
    set_active_spine_accessor(current)
    return current


def resolve_active_spine() -> EventSpine | None:
    """Return the active ``EventSpine``, or ``None`` when unwired."""
    getter = _read_spine_accessor()
    if getter is None:
        return None
    try:
        return getter()
    except Exception as exc:
        log.warning("spine.runtime_hooks: spine accessor raised %r", exc)
        return None


# ── shared emission seam ─────────────────────────────────────────────


def emit_through_pipeline(
    *,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any],
    outcome: OutcomeT | None = None,
    span: Any = None,
    exc: BaseException | None = None,
) -> None:
    """Emit one spine event via direct ``EventSpine.append`` (production path).

    ``EmitPipeline`` is hook-less test surface only (ADR-0194 P2-07).
    When a Session SSOT hook is active, enrichment runs at the Session
    boundary; this funnel only stamps in-process records.
    """
    if exc is not None:
        # Reuse the wrap-side helper so the two emission paths emit
        # identical field names and traceback caps.
        from lca.harness.declarative.compile.instrument.wrap import (
            _exception_payload,
        )

        payload = {**_exception_payload(exc), **payload}
    spine = resolve_active_spine()
    if spine is None:
        return
    _emit_spine_direct(
        spine=spine,
        execution_point=execution_point,
        channel=channel,
        payload=payload,
        outcome=outcome,
        span=span,
    )


# ── ctx_effect ───────────────────────────────────────────────────────


def install_ctx_effect_hook(
    ctx: Any,
    *,
    start_execution_point: str,
    end_execution_point: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Emit a lifecycle ``start`` now and an ``end`` when ``ctx`` disposes.

    The teardown emission is registered through ``ctx.effect`` so the
    kernel's existing disposer chain owns it; the hook itself keeps no
    state. Both events go through :func:`emit_through_pipeline`, so a
    ``ctx_effect`` event carries the same auto-source fields as an
    assembler-wrapped phase node.
    """
    base_payload = dict(payload or {})
    span = SpineContext.push_span(start_execution_point)
    emit_through_pipeline(
        execution_point=start_execution_point,
        channel="control",
        payload=base_payload,
        span=span,
    )

    def _emit_end() -> None:
        emit_through_pipeline(
            execution_point=end_execution_point,
            channel="control",
            payload=base_payload,
            outcome="success",
            span=span,
        )
        # Balance the span stack only at teardown: the ctx lifetime *is*
        # the span, so I13's push/pop pairing spans the whole context.
        try:
            SpineContext.pop_span(start_execution_point)
        except Exception as exc:
            log.warning("spine.runtime_hooks: ctx_effect span unwind failed: %s", exc)

    ctx.effect(_emit_end, label=f"spine.ctx_effect:{start_execution_point}")


# ── ctx_intercept ────────────────────────────────────────────────────


def wrap_ctx_intercept(
    fn: Callable[..., Any],
    *,
    execution_point_start: str,
    execution_point_end: str,
) -> Callable[..., Any]:
    """Wrap ``fn`` so each call brackets itself with pipeline-fed events.

    Sync and async callables are both supported. The wrapper carries the
    ``__lca_instrumented__`` marker plus
    ``wrap_provenance = "ctx_intercept"`` so a catalog can tell an
    intercepted host method from an assembler-wrapped phase node.
    """
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            span = SpineContext.push_span(execution_point_start)
            emit_through_pipeline(
                execution_point=execution_point_start,
                channel="control",
                payload={"args_count": len(args), "kwargs_count": len(kwargs)},
                span=span,
            )
            try:
                result = await fn(*args, **kwargs)
            except BaseException as exc:
                emit_through_pipeline(
                    execution_point=execution_point_end,
                    channel="error",
                    payload={},
                    outcome="failure",
                    span=span,
                    exc=exc,
                )
                SpineContext.pop_span(execution_point_start)
                raise
            emit_through_pipeline(
                execution_point=execution_point_end,
                channel="control",
                payload={},
                outcome="success",
                span=span,
            )
            SpineContext.pop_span(execution_point_start)
            return result

        wrapper: Callable[..., Any] = async_wrapped
    else:

        @functools.wraps(fn)
        def sync_wrapped(*args: Any, **kwargs: Any) -> Any:
            span = SpineContext.push_span(execution_point_start)
            emit_through_pipeline(
                execution_point=execution_point_start,
                channel="control",
                payload={"args_count": len(args), "kwargs_count": len(kwargs)},
                span=span,
            )
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                emit_through_pipeline(
                    execution_point=execution_point_end,
                    channel="error",
                    payload={},
                    outcome="failure",
                    span=span,
                    exc=exc,
                )
                SpineContext.pop_span(execution_point_start)
                raise
            emit_through_pipeline(
                execution_point=execution_point_end,
                channel="control",
                payload={},
                outcome="success",
                span=span,
            )
            SpineContext.pop_span(execution_point_start)
            return result

        wrapper = sync_wrapped

    wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
    wrapper.__lca_instrumented__ = True  # type: ignore[attr-defined]
    wrapper.wrap_provenance = CTX_INTERCEPT_PROVENANCE  # type: ignore[attr-defined]
    return wrapper


def install_ctx_intercept_hook(
    ctx: Any,
    *,
    target: Any,
    method_name: str,
    execution_point_start: str,
    execution_point_end: str,
) -> Callable[[], None]:
    """Replace ``target.method_name`` with a pipeline-fed wrapper.

    Returns the un-patch callable, which is also registered with
    ``ctx.effect`` so the kernel restores the host on dispose even when
    the caller drops the return value. Re-installing over an
    already-instrumented attribute is a no-op: the marker check keeps
    double-wrapping (and therefore duplicate events) impossible.
    """
    original = getattr(target, method_name)
    if getattr(original, WRAP_INSTRUMENTED_ATTR, False):

        def _already_wrapped() -> None:
            return None

        return _already_wrapped

    setattr(
        target,
        method_name,
        wrap_ctx_intercept(
            original,
            execution_point_start=execution_point_start,
            execution_point_end=execution_point_end,
        ),
    )

    def _restore() -> None:
        setattr(target, method_name, original)

    ctx.effect(_restore, label=f"spine.ctx_intercept:{method_name}")
    return _restore


__all__ = [
    "CTX_EFFECT_PROVENANCE",
    "CTX_INTERCEPT_PROVENANCE",
    "emit_through_pipeline",
    "install_ctx_effect_hook",
    "install_ctx_intercept_hook",
    "resolve_active_spine",
    "wrap_ctx_intercept",
]
