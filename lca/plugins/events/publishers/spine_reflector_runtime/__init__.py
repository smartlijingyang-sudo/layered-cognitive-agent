"""spine_reflector_runtime — ADR-0181 PR-3。

PR-3：runtime 全量迁（exception + lifecycle + runtime.observed）。

旧 lca/plugins/observability/spine/reflectors/runtime.py 全部 8 emit
下沉到 EventBus.publish：
- exception.caught / exception.finally / lifecycle.finally (PR-3 本)
- runtime.reducer.apply / runtime.checkpoint.create /
  runtime.resume.start / runtime.resume.end /
  runtime.event_publisher.publish (PR-3 + 旧 reflector 一起删)

signature 严格对齐旧 reflector，调用方零改动（仅 import 路径换）。
"""

from lca.plugins.events.publishers.spine_reflector_runtime.plugin import (
    ReflectorClass,
    emit_exception_caught,
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
    "emit_exception_caught",
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
