"""spine_writable_matrix — ADR-0181 PR-10 (收尾)。

writable_matrix cursor 走 spine_reflector_writable 的 typed 入口。
本 plugin 是 cursor 的 EventMechanism 入口骨架：旧 cursor._spine.append
路径由 EventMechanism.send(SpineEventPayload, plugin=WritableMatrixPlugin)
接管。

删-when：cursor 完全切到 EventMechanism.send（rg
lca.infrastructure.observability.loop_cursor lca/ 路径 → 看
self._spine.append lca/ = 0 触发）。
"""

from lca.plugins.events.publishers.spine_writable_matrix.plugin import (
    WritableMatrixPlugin,
)

__all__ = ["WritableMatrixPlugin"]
