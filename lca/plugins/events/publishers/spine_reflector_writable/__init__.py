"""spine_reflector_writable — ADR-0181 PR-5 / ADR-0183 PR-7。

writable matrix 全迁（7 EP）：
- writable.step.start / .end
- writable.segment.start / .end
- writable.iteration.halt / .closing / .close

签名与旧 lca/plugins/observability/spine/reflectors/source.py 对齐（实际
emit 通过 cursor._append + WritePort 走，PR-5 提供 typed publisher 作为
EventBus 兜底入口）。
"""

from lca.plugins.events.publishers.spine_reflector_writable.plugin import (
    ReflectorClass,
    emit_writable_iteration_close,
    emit_writable_iteration_closing,
    emit_writable_iteration_halt,
    emit_writable_segment_end,
    emit_writable_segment_start,
    emit_writable_step_end,
    emit_writable_step_start,
)

__all__ = [
    "ReflectorClass",
    "emit_writable_iteration_close",
    "emit_writable_iteration_closing",
    "emit_writable_iteration_halt",
    "emit_writable_segment_end",
    "emit_writable_segment_start",
    "emit_writable_step_end",
    "emit_writable_step_start",
]
