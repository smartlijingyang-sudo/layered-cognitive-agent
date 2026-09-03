"""spine_reflector_kernel_loop — ADR-0181 PR-4。

kernel.boot + loop.fork 全迁（3 EP）：
- kernel.boot.start / .completed
- loop.fork
"""

from lca.plugins.events.publishers.spine_reflector_kernel_loop.plugin import (
    ReflectorClass,
    emit_kernel_boot_completed,
    emit_kernel_boot_start,
    emit_loop_fork,
)

__all__ = [
    "ReflectorClass",
    "emit_kernel_boot_completed",
    "emit_kernel_boot_start",
    "emit_loop_fork",
]
