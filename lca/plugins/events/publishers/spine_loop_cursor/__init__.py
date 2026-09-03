"""spine_loop_cursor — ADR-0181 PR-10 (收尾)。

cursor phase.fold 系列 + step.record 系列 走本 publisher 的 EventMechanism
入口骨架。删-when 同 spine_writable_matrix（cursor 完全切 EventMechanism）。
"""

from lca.plugins.events.publishers.spine_loop_cursor.plugin import LoopCursorPlugin

__all__ = ["LoopCursorPlugin"]
