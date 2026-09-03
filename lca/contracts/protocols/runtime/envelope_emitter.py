"""EnvelopeEmitter Protocol — runtime-bound emit helpers (ADR-0177).

The runtime and agent layers historically reached into the spine plugin
tree (``lca.plugins.observability.spine.reflectors.runtime``,
``...agent_spawn``) for envelope-emit helpers.  That inverted the
dependency direction (``runtime → plugin.observability``) and forced
every emit helper to be lazily imported inside each call site.

PR-3 把 envelope emitter helper 迁到
``lca.plugins.events.publishers.spine_reflector_runtime`` /
``spine_reflector_agent_spawn``（PR-4）；旧 plugin 树上的 reflector 文件
随 PR-9 一起退役。本 Protocol 描述的 capability 形态不变：plugin tree
提供实现，runtime 通过 ``DeclarativeRuntimeBindings`` 消费。
Call sites 用 ``self._bindings.envelope.emit_*`` 取代 inline imports。

Default implementation: ``lca/runtime/envelope_emitter.py::SpineEnvelopeEmitter``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from lca.contracts.observability import ExceptionRecord


class EnvelopeEmitter(Protocol):
    """SSOT for runtime/agent envelope-emit helpers (ADR-0177).

    All methods MUST be no-ops when no spine is wired — the existing
    reflector helpers silently swallow spine-write failures, and this
    Protocol preserves that behaviour so call sites can fire-and-forget.

    ``emit_exception_caught`` is the only method that carries structured
    content: it receives an :class:`ExceptionRecord` that the caller MUST
    produce via ``lca.contracts.observability.exc_to_record`` (ADR-0169
    SSOT). Implementations forward the record to the single emitter
    ``lca.infrastructure.observability.spine.exception_emit``; 4-key
    keyword payloads are forbidden because they drop ``traceback_text`` /
    ``call_frames`` / ``err_kind``.
    """

    def emit_reducer_apply_start(self, *, method: str) -> None: ...
    def emit_reducer_apply_end(self, *, method: str, outcome: str) -> None: ...

    def emit_checkpoint_create(self, *, plan_ref: str, state_ref: str, node_id: str) -> None: ...

    def emit_resume_start(self, *, plan_ref: str, state_ref: str, node_id: str) -> None: ...
    def emit_resume_end(
        self, *, plan_ref: str, state_ref: str, node_id: str, outcome: str
    ) -> None: ...

    def emit_lifecycle_finally(self, *, boundary: str, trace_id: str) -> None: ...
    def emit_exception_caught(self, record: ExceptionRecord) -> None: ...
    def emit_exception_finally(self, *, boundary: str, trace_id: str, outcome: str) -> None: ...

    def emit_agent_loop_iteration_start(self, *, trace_id: str, role: str, kind: str) -> None: ...
    def emit_agent_loop_iteration_end(
        self, *, trace_id: str, role: str, kind: str, outcome: str
    ) -> None: ...

    def emit_event_publisher_publish(
        self, *, event_type: str, trace_id: str, outcome: str
    ) -> None: ...


__all__ = ["EnvelopeEmitter"]
