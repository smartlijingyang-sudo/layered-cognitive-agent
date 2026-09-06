"""SpineEnvelopeEmitter — default EnvelopeEmitter impl via FactGateway (ADR-0194 P2-10).

Runtime envelope EPs route through ``lca.infrastructure.session.runtime_emit``
(``publish_ep_bound``). Agent-loop iteration EPs still delegate to
``spine_reflector_agent_spawn`` until P2-14.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any, TypeVar

from lca.infrastructure.session.runtime_emit import (
    emit_exception_finally,
    emit_lifecycle_finally,
    emit_runtime_checkpoint_create,
    emit_runtime_event_publisher_publish,
    emit_runtime_reducer_apply_end,
    emit_runtime_reducer_apply_start,
    emit_runtime_resume_end,
    emit_runtime_resume_start,
)

_F = TypeVar("_F", bound=Callable[..., Any])


class SpineEnvelopeEmitter:
    """Default :class:`EnvelopeEmitter` that delegates runtime EPs to FactGateway."""

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
        self._safe_emit(emit_runtime_reducer_apply_start, method=method)

    def emit_reducer_apply_end(self, *, method: str, outcome: str) -> None:
        self._safe_emit(emit_runtime_reducer_apply_end, method=method, outcome=outcome)

    def emit_checkpoint_create(self, *, plan_ref: str, state_ref: str, node_id: str) -> None:
        self._safe_emit(
            emit_runtime_checkpoint_create,
            plan_ref=plan_ref,
            state_ref=state_ref,
            node_id=node_id,
        )

    def emit_resume_start(self, *, plan_ref: str, state_ref: str, node_id: str) -> None:
        self._safe_emit(
            emit_runtime_resume_start,
            plan_ref=plan_ref,
            state_ref=state_ref,
            node_id=node_id,
        )

    def emit_resume_end(
        self, *, plan_ref: str, state_ref: str, node_id: str, outcome: str
    ) -> None:
        self._safe_emit(
            emit_runtime_resume_end,
            plan_ref=plan_ref,
            state_ref=state_ref,
            node_id=node_id,
            outcome=outcome,
        )

    def emit_lifecycle_finally(self, *, boundary: str, trace_id: str) -> None:
        self._safe_emit(emit_lifecycle_finally, boundary=boundary, trace_id=trace_id)

    def emit_exception_finally(self, *, boundary: str, trace_id: str, outcome: str) -> None:
        self._safe_emit(
            emit_exception_finally,
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
            emit_runtime_event_publisher_publish,
            event_type=event_type,
            trace_id=trace_id,
            outcome=outcome,
        )


__all__ = ["SpineEnvelopeEmitter"]
