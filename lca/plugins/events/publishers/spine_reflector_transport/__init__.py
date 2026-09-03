"""spine_reflector_transport — ADR-0181 PR-4。

transport / kernel 全迁（4 EP）：
- transport.route.enter / .exit
- transport.sse.publish
- kernel.run.start / .stop / .cancelled
（carrier exception.finally 走 spine_reflector_runtime.exception，
不属于本 plugin）
"""

from lca.plugins.events.publishers.spine_reflector_transport.plugin import (
    ReflectorClass,
    emit_kernel_run_cancelled,
    emit_kernel_run_start,
    emit_kernel_run_stop,
    emit_transport_route_enter,
    emit_transport_route_exit,
    emit_transport_sse_publish,
)

__all__ = [
    "ReflectorClass",
    "emit_kernel_run_cancelled",
    "emit_kernel_run_start",
    "emit_kernel_run_stop",
    "emit_transport_route_enter",
    "emit_transport_route_exit",
    "emit_transport_sse_publish",
]
