"""EnvelopeEmitter Protocol — runtime-bound emit helpers (ADR-0177).

Runtime and agent call sites consume envelope-emit helpers through
``DeclarativeRuntimeBindings.envelope`` rather than importing the plugin
tree. Plugin implementations live under
``lca.plugins.events.publishers.spine_reflector_runtime`` and
``spine_reflector_agent_spawn``.

Default implementation: ``lca/runtime/envelope_emitter.py::SpineEnvelopeEmitter``.

``exception.caught`` is not on this Protocol. That EP carries a
normalized :class:`~lca.contracts.observability.ExceptionRecord` and
belongs to ``lca.infrastructure.observability.spine.exception_emit``.
Envelope methods are empty start/end or finally markers; they cannot
carry the record's traceback fields.
"""

from __future__ import annotations

from typing import Protocol


class EnvelopeEmitter(Protocol):
    """SSOT for runtime/agent envelope-emit helpers (ADR-0177).

    All methods MUST be no-ops when no spine is wired — the existing
    reflector helpers silently swallow spine-write failures, and this
    Protocol preserves that behaviour so call sites can fire-and-forget.

    Methods on this Protocol are empty envelopes (reducer apply, resume,
    lifecycle finally, agent-loop iteration). ``exception.caught`` is
    observability, not envelope forwarding: callers normalize via
    ``exc_to_record`` and the single emitter in
    ``lca.infrastructure.observability.spine.exception_emit``.
    """

    def emit_reducer_apply_start(self, *, method: str) -> None: ...
    def emit_reducer_apply_end(self, *, method: str, outcome: str) -> None: ...

    def emit_checkpoint_create(self, *, plan_ref: str, state_ref: str, node_id: str) -> None: ...

    def emit_resume_start(self, *, plan_ref: str, state_ref: str, node_id: str) -> None: ...
    def emit_resume_end(
        self, *, plan_ref: str, state_ref: str, node_id: str, outcome: str
    ) -> None: ...

    def emit_lifecycle_finally(self, *, boundary: str, trace_id: str) -> None: ...
    def emit_exception_finally(self, *, boundary: str, trace_id: str, outcome: str) -> None: ...

    def emit_agent_loop_iteration_start(self, *, trace_id: str, role: str, kind: str) -> None: ...
    def emit_agent_loop_iteration_end(
        self, *, trace_id: str, role: str, kind: str, outcome: str
    ) -> None: ...

    def emit_event_publisher_publish(
        self, *, event_type: str, trace_id: str, outcome: str
    ) -> None: ...


__all__ = ["EnvelopeEmitter"]
