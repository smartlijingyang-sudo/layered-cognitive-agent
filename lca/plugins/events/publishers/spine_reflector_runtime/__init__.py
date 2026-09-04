"""spine_reflector_runtime — ADR-0181 PR-3。

Runtime envelope emits 下沉到 EventBus.publish：
- exception.finally / lifecycle.finally
- runtime.reducer.apply / runtime.checkpoint.create /
  runtime.resume.start / runtime.resume.end /
  runtime.event_publisher.publish / runtime.observed

``exception.caught`` is not re-exported. Callers use
``lca.infrastructure.observability.spine.exception_emit``.
"""

from lca.plugins.events.publishers.spine_reflector_runtime.plugin import (
    ReflectorClass,
    emit_exception_finally,
    emit_lifecycle_finally,
    emit_runtime_checkpoint_create,
    emit_runtime_event_publisher_publish,
    emit_runtime_reducer_apply_end,
    emit_runtime_reducer_apply_start,
    emit_runtime_resume_end,
    emit_runtime_resume_start,
    set_active_run_id,
)

__all__ = [
    "ReflectorClass",
    "emit_exception_finally",
    "emit_lifecycle_finally",
    "emit_runtime_checkpoint_create",
    "emit_runtime_event_publisher_publish",
    "emit_runtime_reducer_apply_end",
    "emit_runtime_reducer_apply_start",
    "emit_runtime_resume_end",
    "emit_runtime_resume_start",
    "set_active_run_id",
]
