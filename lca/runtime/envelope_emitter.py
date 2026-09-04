"""SpineEnvelopeEmitter — default EnvelopeEmitter impl backed by spine reflectors (ADR-0177).

The spine plugin tree owns the actual emit helpers
(``lca.plugins.events.publishers.spine_reflector_{runtime,agent_spawn}``).
This module wraps them in the :class:`EnvelopeEmitter` Protocol so that
``runtime`` and ``agent`` layers can use a bound capability instead of
inline-importing the plugin tree.

When no spine is wired, the wrapped reflectors silently no-op (the
plugin tree documents that behaviour); this class preserves it.

``exception.caught`` is not forwarded here. Callers normalize via
``exc_to_record`` and
``lca.infrastructure.observability.spine.exception_emit``.

The class lives in ``lca/runtime/`` because it is consumed exclusively
by the runtime/agent layers as a default-impl seam; it lazy-imports
the plugin tree so it does not invert the dependency direction at import
time.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])


class SpineEnvelopeEmitter:
    """Default :class:`EnvelopeEmitter` that lazily delegates to spine reflectors."""

    @staticmethod
    def _runtime() -> Any:
        from lca.plugins.events.publishers.spine_reflector_runtime import (
            plugin as _r,
        )

        return _r

    @staticmethod
    def _agent_spawn() -> Any:
        from lca.plugins.events.publishers.spine_reflector_agent_spawn import (
            plugin as _a,
        )

        return _a

    def _safe_emit(self, fn: _F, /, **kwargs: Any) -> None:
        with contextlib.suppress(BaseException):
            fn(**kwargs)

    def emit_reducer_apply_start(self, *, method: str) -> None:
        self._safe_emit(self._runtime().emit_runtime_reducer_apply_start, method=method)

    def emit_reducer_apply_end(self, *, method: str, outcome: str) -> None:
        self._safe_emit(
            self._runtime().emit_runtime_reducer_apply_end,
            method=method,
            outcome=outcome,
        )

    def emit_checkpoint_create(self, *, plan_ref: str, state_ref: str, node_id: str) -> None:
        self._safe_emit(
            self._runtime().emit_runtime_checkpoint_create,
            plan_ref=plan_ref,
            state_ref=state_ref,
            node_id=node_id,
        )

    def emit_resume_start(self, *, plan_ref: str, state_ref: str, node_id: str) -> None:
        self._safe_emit(
            self._runtime().emit_runtime_resume_start,
            plan_ref=plan_ref,
            state_ref=state_ref,
            node_id=node_id,
        )

    def emit_resume_end(self, *, plan_ref: str, state_ref: str, node_id: str, outcome: str) -> None:
        self._safe_emit(
            self._runtime().emit_runtime_resume_end,
            plan_ref=plan_ref,
            state_ref=state_ref,
            node_id=node_id,
            outcome=outcome,
        )

    def emit_lifecycle_finally(self, *, boundary: str, trace_id: str) -> None:
        self._safe_emit(
            self._runtime().emit_lifecycle_finally,
            boundary=boundary,
            trace_id=trace_id,
        )

    def emit_exception_finally(self, *, boundary: str, trace_id: str, outcome: str) -> None:
        self._safe_emit(
            self._runtime().emit_exception_finally,
            boundary=boundary,
            trace_id=trace_id,
            outcome=outcome,
        )

    def emit_agent_loop_iteration_start(self, *, trace_id: str, role: str, kind: str) -> None:
        self._safe_emit(
            self._agent_spawn().emit_agent_loop_iteration_start,
            trace_id=trace_id,
            role=role,
            iteration_kind=kind,
        )

    def emit_agent_loop_iteration_end(
        self, *, trace_id: str, role: str, kind: str, outcome: str
    ) -> None:
        self._safe_emit(
            self._agent_spawn().emit_agent_loop_iteration_end,
            trace_id=trace_id,
            role=role,
            iteration_kind=kind,
            outcome=outcome,
        )

    def emit_event_publisher_publish(self, *, event_type: str, trace_id: str, outcome: str) -> None:
        self._safe_emit(
            self._runtime().emit_runtime_event_publisher_publish,
            event_type=event_type,
            trace_id=trace_id,
            outcome=outcome,
        )


__all__ = ["SpineEnvelopeEmitter"]
