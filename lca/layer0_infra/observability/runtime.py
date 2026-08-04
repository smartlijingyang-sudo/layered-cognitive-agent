"""Telemetry runtime — long-term ambient model (OTel-style, no dual paths).

Architecture
------------
contracts
  Observability  — sink: emit_span(TraceSpan)
  Telemetry      — app facade: span(name, **attrs)
  SpanName/ATTR  — closed vocabulary

L0 (this module)
  ContextTelemetry  — Telemetry impl over an Observability sink
  bind(obs)         — install ambient Telemetry for the call stack
  span(...)         — emit via ambient Telemetry (default: NullTelemetry)

Correlation (trace_id / parent_span_id) lives in contextvars, owned only here.
Business layers never touch Observability or SpanScope; they only call bind/span.

Composition rule
----------------
TeamHandle.run / CognitiveAgent.run **always** ``bind`` at the edge.
Nested components (hooks, tools, transport, LLM wrapper) only call ``span``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from lca.contracts.enums import SpanStatus
from lca.contracts.ids import new_id, utc_now
from lca.contracts.observability import TraceSpan
from lca.contracts.protocols import Observability, Telemetry
from lca.contracts.telemetry import ATTR_AGENT_ROLE, ATTR_STEP
from lca.layer0_infra.observability.null_observability import NullObservability

# ── correlation ──────────────────────────────────────────────
_trace_id: ContextVar[str | None] = ContextVar("lca_trace_id", default=None)
_parent_span_id: ContextVar[str | None] = ContextVar("lca_parent_span_id", default=None)
_telemetry: ContextVar[Telemetry | None] = ContextVar("lca_telemetry", default=None)

# ── ambient actor (OTel baggage-style) ─────────────
# Set at the hook-trigger boundary of the cognitive loop; spans that carry no
# explicit agent_role/step attribute pick these up so every span is
# self-describing (required for stateless narrative sectioning). ContextVars
# are copied per asyncio task, so concurrent members stay isolated.
_actor_role: ContextVar[str] = ContextVar("lca_actor_role", default="")
_actor_step: ContextVar[int | None] = ContextVar("lca_actor_step", default=None)


def set_actor(role: str, step: int | None) -> None:
    """Update the ambient actor identity for spans emitted from this context."""
    _actor_role.set(role or "")
    _actor_step.set(step)


@dataclass(frozen=True)
class SpanContext:
    trace_id: str | None
    parent_span_id: str | None


def get_span_context() -> SpanContext:
    return SpanContext(trace_id=_trace_id.get(), parent_span_id=_parent_span_id.get())


# ── span engine (package-private; not part of public app API) ─


class _Span:
    """Context manager yielding a TraceSpan; ends + emits on exit."""

    def __init__(
        self,
        backend: Observability,
        name: str,
        *,
        trace_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self._backend = backend
        self._name = name
        self._explicit_trace = trace_id
        self._attributes = dict(attributes or {})
        self._record: TraceSpan | None = None
        self._trace_token: Token[str | None] | None = None
        self._parent_token: Token[str | None] | None = None

    def __enter__(self) -> TraceSpan:
        parent = _parent_span_id.get()
        trace_id = self._explicit_trace or _trace_id.get() or new_id("trace")
        span_id = new_id("span")
        self._autofill_actor()
        self._record = TraceSpan(
            span_id=span_id,
            trace_id=trace_id,
            name=self._name,
            started_at=utc_now(),
            parent_span_id=parent,
            attributes=self._attributes,
        )
        self._trace_token = _trace_id.set(trace_id)
        self._parent_token = _parent_span_id.set(span_id)
        return self._record

    def _autofill_actor(self) -> None:
        """Stamp ambient actor identity onto spans that lack it.

        Explicit attributes win; only missing ``agent_role``/``step`` are filled
        so llm.chat / tool.execute / transport spans become self-describing.
        """
        if ATTR_AGENT_ROLE not in self._attributes:
            role = _actor_role.get()
            if role:
                self._attributes[ATTR_AGENT_ROLE] = role
        if ATTR_STEP not in self._attributes:
            step = _actor_step.get()
            if step is not None:
                self._attributes[ATTR_STEP] = step

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del tb
        if self._record is not None:
            self._record.ended_at = utc_now()
            if exc is not None:
                self._record.status = SpanStatus.ERROR
                self._record.attributes.setdefault(
                    "error_type",
                    exc_type.__name__ if exc_type is not None else type(exc).__name__,
                )
                self._record.attributes.setdefault("error_message", str(exc)[:500])
            self._backend.emit_span(self._record)
        if self._parent_token is not None:
            _parent_span_id.reset(self._parent_token)
        if self._trace_token is not None:
            _trace_id.reset(self._trace_token)


# ── Telemetry implementations ────────────────────────────────


class ContextTelemetry:
    """Default Telemetry: one Observability sink + correlation stack."""

    def __init__(self, backend: Observability) -> None:
        self._backend = backend

    def span(self, name: str, **attributes: Any) -> _Span:
        trace_id = attributes.pop("trace_id", None)
        tid = trace_id if isinstance(trace_id, str) else None
        return _Span(self._backend, name, trace_id=tid, attributes=attributes)


class NullTelemetry:
    """Always-available default; spans go to NullObservability."""

    __slots__ = ("_backend",)

    def __init__(self) -> None:
        self._backend = NullObservability()

    def span(self, name: str, **attributes: Any) -> _Span:
        trace_id = attributes.pop("trace_id", None)
        tid = trace_id if isinstance(trace_id, str) else None
        return _Span(self._backend, name, trace_id=tid, attributes=attributes)


_DEFAULT: Telemetry = NullTelemetry()


def current() -> Telemetry:
    """Ambient Telemetry (never None — NullTelemetry when unbound)."""
    return _telemetry.get() or _DEFAULT


@contextmanager
def bind(observability: Observability) -> Iterator[Telemetry]:
    """Install ambient Telemetry for this call stack (re-entrant)."""
    tel: Telemetry = ContextTelemetry(observability)
    token = _telemetry.set(tel)
    try:
        yield tel
    finally:
        _telemetry.reset(token)


def span(name: str | Any, **attributes: Any) -> _Span:
    """Open a child span on the ambient Telemetry.

    ``name`` may be ``SpanName`` or str. Yields ``TraceSpan`` (mutable attributes).
    """
    label = name.value if hasattr(name, "value") else str(name)
    opened = current().span(label, **attributes)
    if isinstance(opened, _Span):
        return opened
    # Defensive: Protocol 返回类型为 Any；非法实现时降级为空 sink span
    return _Span(NullObservability(), label, attributes=attributes)
