"""Runtime spine reflector — PR-3.4 + Task 7.3 (``RuntimeFieldProducer``).

Emits canonical ``EXECUTION_POINTS`` events for the runtime layer
boundaries (PR-3.4) AND contributes the runtime axis of the D11
auto-source scheme via :class:`RuntimeFieldProducer` (Task 7.3 /
ADR-0165.1 §7.5).

PR-3.4 emit helpers
-------------------

- ``runtime.reducer.apply``       — around every Reducer.apply_* call
- ``runtime.checkpoint.create``   — when a DeclarativeCheckpoint is built
- ``runtime.resume.start`` / ``end`` — bracketing a resumed Turn
- ``runtime.event_publisher.publish`` — each lifecycle publisher.publish
- ``exception.caught``            — when the runner raises before re-raise
- ``exception.finally``            — paired with every ``exception.caught``

Pattern
-------
Mirrors :mod:`lca.plugins.observability.spine.reflectors.cognition`:
the runtime layer never receives the spine through its Protocol
surface. Profile boot installs the run's EventSpine via
``set_active_spine``; every call to a tiny ``emit_*`` helper here
forwards to ``spine.append`` if a spine is wired, otherwise returns
silently.

FD-1 / FD-2 containment
-----------------------
- ``_safe_append`` swallows ``EventRecord`` validation errors (malformed
  payload) so a broken helper never blocks the caller; logs at WARNING.
- Sink-level failures propagate as FD-1 fail-fast and are surfaced by
  the spine itself; helpers never add another failure surface above it.
- The middleware wrappers around Reducer methods re-raise inner
  exceptions; only the *envelope* of the failure becomes a
  ``.end`` event with ``outcome="failure"``.

Scope
-----
This module imports only the public spine surface
(``EventSpine``, ``SpineContext``, ``Outcome``, ``Channel``) and never
the legacy ``journal.{engine,backends,stream,step}`` modules — those
are forbidden by the brief.

Task 7.3 — :class:`RuntimeFieldProducer`
----------------------------------------
Per ADR-0165.1 §7.5 (D11 auto-source), the runtime axis of the
four-axis auto-source scheme (signature / context / runtime /
manifest) is owned by :class:`RuntimeFieldProducer`. The producer
contributes five keys into ``EventRecord.payload`` on the post-phase:

- ``return_value_fingerprint`` — ``sha256(repr(return_value))``
- ``duration_ms``              — ``time.monotonic()`` diff across pre/post
- ``input_fingerprint``        — ``sha256(repr(args + kwargs))``
- ``when_corrected``           — NTP-corrected timestamp (placeholder)
- ``prev_event_hash``          — ``SpineContext.last_hash()``

The producer is post-phase only; pre/exception phases return ``{}``
so the timing, fingerprint, and chain-link slots stay end-of-call
concerns. Profile boot installs the producer through :func:`setup`
(``ctx.provide("field_producer.runtime", RuntimeFieldProducer())``);
``EmitPipeline`` fetches it and merges its keys into the assembled
``EventRecord.payload``.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.observability.spine.producer import Phase
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
)
from lca.infrastructure.observability.spine.event_spine import EventSpine

log = logging.getLogger(__name__)


# ── process-local active spine accessor ─────────────────────────────
#
# Mirrors cognition.py so cognition, runtime, and other reflectors can
# share the same wiring call. Profile boot installs the run's
# EventSpine here so every runtime boundary can locate it without
# changing any constructor signature.

_active_spine: EventSpine | None = None


def set_active_spine(spine: EventSpine | None) -> None:
    """Install or clear the process-local active spine for runtime EPs.

    Called by profile boot at the start of a run. Tests call it
    directly to wire a capturing spine. Passing ``None`` clears.
    """
    global _active_spine
    _active_spine = spine


# ADR-2026-09-02-i17-traceback §D5: the runtime reflector needs to
# thread the active run_id into its events. Tests already wire
# ``set_active_spine``; we mirror that pattern with
# ``set_active_run_id`` so the runtime reflector can stamp payload
# ``run_id`` without changing every reducer call site. Hot path
# stays a single ``globals()`` lookup in `_coerce_run_id`.

_active_run_id: str = ""


def set_active_run_id(run_id: str | None) -> None:
    """Install the active run_id for runtime EP payloads.

    Setting ``None`` clears (the helper stores ``""``). Profile boot
    calls this once per run; tests can call it directly.
    """
    global _active_run_id
    _active_run_id = str(run_id or "")


def _coerce_run_id(explicit: str | None) -> str:
    """Resolve ``run_id`` with explicit-first, active-fallback semantics.

    The reducer's ``_instrument_apply`` decorator does not receive
    the active run_id as an argument (state is the only handle it
    has, and the state object is application-level). Using a
    process-local accessor keeps the call site unchanged while still
    landing the correct id on the journal.
    """
    return str(explicit or "") or _active_run_id


def get_active_spine() -> EventSpine | None:
    """Return the active spine, or ``None`` if no run is in flight."""
    return _active_spine


# ── core emitter ─────────────────────────────────────────────────────


def _safe_append(
    *,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any] | None = None,
    outcome: Outcome | None = None,
) -> EventRecord | None:
    """Dispatch to the active spine, returning ``None`` when no spine wired.

    Swallows ``EventRecord`` validation errors (malformed payload) so a
    broken helper never blocks the caller; logs at WARNING. All other
    exceptions propagate as FD-1.
    """
    spine = _active_spine
    if spine is None:
        return None
    try:
        return spine.append(
            execution_point=execution_point,
            channel=channel,
            caller_payload=payload,
            outcome=outcome,
        )
    except ValueError as exc:
        log.warning(
            "runtime_reflector: drop invalid event ep=%s err=%s",
            execution_point,
            exc,
        )
        return None


# ── runtime.reducer.apply ───────────────────────────────────────────
#
# The Reducer Protocol is the C4 single-writer for AgentState (ADR-0070).
# Every ``apply_*`` fold is a fact mutation boundary, so the spine
# captures one event per call with the reducer method name in payload.


def emit_runtime_reducer_apply_start(
    *,
    method: str,
    run_id: str | None = None,
) -> EventRecord | None:
    """Emit ``runtime.reducer.apply`` start-side marker for one apply_* call."""
    return _safe_append(
        execution_point="runtime.reducer.apply",
        channel="fact",
        payload={
            "method": method,
            "phase": "start",
            "run_id": _coerce_run_id(run_id),
        },
    )


def emit_runtime_reducer_apply_end(
    *,
    method: str,
    outcome: Outcome,
    run_id: str | None = None,
) -> EventRecord | None:
    """Emit ``runtime.reducer.apply`` end-side marker for one apply_* call."""
    return _safe_append(
        execution_point="runtime.reducer.apply",
        channel="fact",
        payload={
            "method": method,
            "phase": "end",
            "run_id": _coerce_run_id(run_id),
        },
        outcome=outcome,
    )


# ── runtime.checkpoint.create ───────────────────────────────────────


def emit_runtime_checkpoint_create(
    *,
    plan_ref: str,
    state_ref: str,
    node_id: str,
    outcome: Outcome = "success",
) -> EventRecord | None:
    """Emit when a DeclarativeCheckpoint is materialised for resume."""
    return _safe_append(
        execution_point="runtime.checkpoint.create",
        channel="control",
        payload={
            "plan_ref": plan_ref,
            "state_ref": state_ref,
            "node_id": node_id,
        },
        outcome=outcome,
    )


# ── runtime.resume.start / runtime.resume.end ───────────────────────


def emit_runtime_resume_start(
    *,
    plan_ref: str,
    state_ref: str,
    node_id: str,
) -> EventRecord | None:
    """Emit at the entry of CognitiveRuntime.resume before driver handoff."""
    return _safe_append(
        execution_point="runtime.resume.start",
        channel="control",
        payload={
            "plan_ref": plan_ref,
            "state_ref": state_ref,
            "node_id": node_id,
        },
    )


def emit_runtime_resume_end(
    *,
    plan_ref: str,
    state_ref: str,
    node_id: str,
    outcome: Outcome,
) -> EventRecord | None:
    """Emit at the end of CognitiveRuntime.resume after driver handoff.

    ``outcome`` is ``"success"`` on a normal terminal return; ``"failure"``
    if the driver raised; ``"cancelled"`` if asyncio.CancelledError.
    """
    return _safe_append(
        execution_point="runtime.resume.end",
        channel="control",
        payload={
            "plan_ref": plan_ref,
            "state_ref": state_ref,
            "node_id": node_id,
        },
        outcome=outcome,
    )


# ── runtime.event_publisher.publish ────────────────────────────────
#
# Wraps each call into the legacy RuntimeLifecyclePublisher so the spine
# carries a parallel fact stream alongside the existing subscriber chain.


def emit_runtime_event_publisher_publish(
    *,
    event_type: str,
    trace_id: str,
    outcome: Outcome = "success",
) -> EventRecord | None:
    """Emit at every call to ``RuntimeLifecyclePublisher.publish``."""
    return _safe_append(
        execution_point="runtime.event_publisher.publish",
        channel="control",
        payload={"event_type": event_type, "trace_id": trace_id},
        outcome=outcome,
    )


# ── exception.caught / exception.finally ────────────────────────────
#
# ``exception.caught`` is emitted when the runner raises and the runtime
# decides to forward it. ``exception.finally`` is the paired envelope
# emitted after the upstream handler has logged the boundary event so
# downstream consumers can rely on a strict start/end pair for cleanup.


def emit_exception_caught(
    *,
    boundary: str,
    exc_type: str,
    message: str,
    trace_id: str | None = None,
) -> EventRecord | None:
    """Emit when the runtime layer catches an exception at a known boundary.

    ``boundary`` is one of a small enum (e.g. ``"resume"``,
    ``"terminal_driver"``). ``exc_type`` is the qualified class name.
    """
    return _safe_append(
        execution_point="exception.caught",
        channel="error",
        payload={
            "boundary": boundary,
            "exc_type": exc_type,
            "message": message,
            "trace_id": trace_id or "",
        },
        outcome="failure",
    )


def emit_exception_finally(
    *,
    boundary: str,
    trace_id: str | None = None,
    outcome: Outcome = "failure",
) -> EventRecord | None:
    """Emit ``exception.finally`` —— 仅异常路径（ADR-0166 S5）。

    正常路径请用 :func:`emit_lifecycle_finally`；本 helper 仅在异常边界
    收口时使用。默认 ``outcome="failure"``；cancelled 也走本 EP。
    """
    return _safe_append(
        execution_point="exception.finally",
        channel="diagnostic",
        payload={
            "boundary": boundary,
            "trace_id": trace_id or "",
        },
        outcome=outcome,
    )


def emit_lifecycle_finally(
    *,
    boundary: str,
    trace_id: str | None = None,
) -> EventRecord | None:
    """Emit ``lifecycle.finally`` —— 正常路径收口（ADR-0166 S5）。

    替代「成功路径也写 ``exception.finally``」的混淆语义；reader
    通过 EP 名区分异常与正常生命周期收口。
    """
    return _safe_append(
        execution_point="lifecycle.finally",
        channel="control",
        payload={
            "boundary": boundary,
            "trace_id": trace_id or "",
        },
        outcome="success",
    )


# ── Task 7.3: ``RuntimeFieldProducer`` — D11 runtime auto-source ─────
#
# See module docstring "Task 7.3" for the full contract.

_FINGERPRINT_ALGO = hashlib.sha256
_MILLIS_PER_SECOND = 1_000.0  # seconds → ms; centralises the conversion


class RuntimeFieldProducer:
    """D11 runtime FieldProducer — end-of-call timing + fingerprint payload.

    Attributes
    ----------
    name:
        Stable identifier used by ``EmitPipeline`` for debug logging
        and assembly-order reporting. Pinned to
        ``"spine.reflector.runtime"`` so it matches the plugin manifest
        id.
    priority:
        Sort key for the merge pipeline. ``30`` sits between the
        signature producer (priority 100, late in merge order) and the
        context producer (priority 20, earlier in merge order) so
        runtime fields can stamp prev_event_hash / when_corrected over
        context keys without colliding with signature fingerprint.
    enabled:
        Profile-level toggle. ``EmitPipeline`` skips disabled producers
        without removing them from the registry.

    Notes
    -----
    The producer is **post-phase only**. ``phase="pre"`` snapshots the
    start monotonic clock and the input fingerprint into instance
    state keyed by ``id(fn)``; ``phase="post"`` computes the diff,
    fingerprints the return value, and reads ``prev_event_hash`` from
    :class:`SpineContext`. Phases outside ``"pre"`` / ``"post"``
    contribute no fields — the exception envelope is owned by the
    classifier producers (see ADR-0165.1 §7.5.2/4).
    """

    name: str = "spine.reflector.runtime"
    priority: int = 30
    enabled: bool = True

    def __init__(self) -> None:
        # Per-fn call state: maps ``id(fn)`` → ``{"start_monotonic": float,
        # "input_fingerprint": str}``. Cleared on each ``post`` call so
        # stale entries never bleed across producer instances.
        self._call_state: dict[int, dict[str, Any]] = {}

    def produce(
        self,
        *,
        fn: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        ctx: Any,
        span: Any,
        phase: Phase,
    ) -> dict[str, Any]:
        """Return the five runtime auto-source keys on the post-phase.

        ``phase`` is part of the ``FieldProducer`` Protocol surface;
        this producer returns ``{}`` for ``"pre"`` companion state and
        ``"exception"``, and the full dict on ``"post"``. The ``ctx``
        argument is consumed via attribute access for the return value
        (``ctx.current_return_value``) and ``span`` is documented unused
        — the chain hash lives on :class:`SpineContext`.
        """
        del span  # documented unused; chain hash lives on SpineContext.

        call_key = id(fn)

        if phase == "pre":
            self._call_state[call_key] = {
                "start_monotonic": time.monotonic(),
                "input_fingerprint": _FINGERPRINT_ALGO(
                    _stable_repr((args, kwargs)).encode("utf-8")
                ).hexdigest(),
            }
            return {}

        if phase != "post":
            return {}

        prior_state = self._call_state.pop(call_key, None)
        if prior_state is None:
            duration_ms = 0.0
            input_fingerprint = _FINGERPRINT_ALGO(
                _stable_repr((args, kwargs)).encode("utf-8")
            ).hexdigest()
        else:
            elapsed_seconds = time.monotonic() - prior_state["start_monotonic"]
            duration_ms = elapsed_seconds * _MILLIS_PER_SECOND
            input_fingerprint = prior_state["input_fingerprint"]

        return_value = getattr(ctx, "current_return_value", None)
        return {
            "return_value_fingerprint": _FINGERPRINT_ALGO(
                _stable_repr(return_value).encode("utf-8")
            ).hexdigest(),
            "duration_ms": duration_ms,
            "input_fingerprint": input_fingerprint,
            "when_corrected": datetime.now(timezone.utc),
            "prev_event_hash": SpineContext.last_hash(),
        }


def _stable_repr(value: Any) -> str:
    """Return a stable, exception-free string representation of ``value``.

    ``repr()`` can raise for objects whose ``__repr__`` is broken; the
    producer must never raise inside the merge path, so any failure
    collapses to the fully-qualified type name (e.g. ``"<ValueError>"``).
    """
    try:
        return repr(value)
    except Exception as exc:  # intentional broad catch — never raise inside merge path
        return f"<{type(exc).__name__}>"


@plugin(
    id="spine.reflector.runtime",
    provides=("field_producer.runtime",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects=EffectClass.NONE,
    description=(
        "Runtime FieldProducer — injects D11 return_value_fingerprint, "
        "duration_ms, input_fingerprint, when_corrected, prev_event_hash "
        "into every spine EventRecord.payload via EmitPipeline merge."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_reflector_runtime",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.read_clock",)),
        observability=EvidenceContract(
            descriptors=("spine.field_producer.runtime",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("emit_pipeline",),
        emits=("field_producer.runtime",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Install a singleton :class:`RuntimeFieldProducer` instance.

    The plugin carries no I/O and no startup work beyond
    ``ctx.provide``; the ``L0`` layer is sufficient because every
    profile that wants D11 runtime coverage just declares this plugin
    in its enables list.
    """
    del config  # accepted for protocol conformance; this plugin is config-free.
    ctx.provide("field_producer.runtime", RuntimeFieldProducer())


__all__ = [
    "RuntimeFieldProducer",
    "emit_exception_caught",
    "emit_exception_finally",
    "emit_lifecycle_finally",
    "emit_runtime_checkpoint_create",
    "emit_runtime_event_publisher_publish",
    "emit_runtime_reducer_apply_end",
    "emit_runtime_reducer_apply_start",
    "emit_runtime_resume_end",
    "emit_runtime_resume_start",
    "get_active_spine",
    "set_active_spine",
    "setup",
]
