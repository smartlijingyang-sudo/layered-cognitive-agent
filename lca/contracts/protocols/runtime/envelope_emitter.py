"""EnvelopeEmitter Protocol — runtime-bound emit helpers (ADR-0177).

The runtime and agent layers historically reached into the spine plugin
tree (``lca.plugins.observability.spine.reflectors.runtime``,
``...agent_spawn``) for envelope-emit helpers.  That inverted the
dependency direction (``runtime → plugin.observability``) and forced
every emit helper to be lazily imported inside each call site.

This Protocol flips the dependency: the plugin tree provides the
implementation; the runtime consumes it through a bound capability on
``DeclarativeRuntimeBindings``.  Call sites use ``self._bindings.envelope.emit_*``
instead of inline imports.

Implementations are provided by the spine plugin tree via
``lca/infrastructure/observability/envelope_emitter.py``.
"""

from __future__ import annotations

from typing import Protocol


class EnvelopeEmitter(Protocol):
    """SSOT for runtime/agent envelope-emit helpers (ADR-0177).

    All methods MUST be no-ops when no spine is wired — the existing
    reflector helpers silently swallow spine-write failures, and this
    Protocol preserves that behaviour so call sites can fire-and-forget.
    """

    def emit_reducer_apply_start(self, *, method: str) -> None: ...
    def emit_reducer_apply_end(self, *, method: str, outcome: str) -> None: ...

    def emit_checkpoint_create(self, *, plan_ref: str, state_ref: str, node_id: str) -> None: ...

    def emit_resume_start(self, *, plan_ref: str, state_ref: str, node_id: str) -> None: ...
    def emit_resume_end(
        self, *, plan_ref: str, state_ref: str, node_id: str, outcome: str
    ) -> None: ...

    def emit_lifecycle_finally(self, *, boundary: str, trace_id: str) -> None: ...
    def emit_exception_caught(
        self, *, boundary: str, exc_type: str, message: str, trace_id: str
    ) -> None: ...
    def emit_exception_finally(self, *, boundary: str, trace_id: str, outcome: str) -> None: ...

    def emit_agent_loop_iteration_start(self, *, trace_id: str, role: str, kind: str) -> None: ...
    def emit_agent_loop_iteration_end(
        self, *, trace_id: str, role: str, kind: str, outcome: str
    ) -> None: ...

    def emit_event_publisher_publish(
        self, *, event_type: str, trace_id: str, outcome: str
    ) -> None: ...


__all__ = ["EnvelopeEmitter"]
