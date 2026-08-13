"""SSEJournalProjector —— journal → SSE 广播投影器（与 console/jsonl 平级）。

零翻译：事件类名即 SSE event 字段。不在这里过滤；过滤发生在 UI 门口。
Gateway 线上读者是 LiveTail；本投影器留给其它入口 / 单测。
"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.observability.journal.sse_frames import stamped_to_sse_frame

EmitFn = Callable[[str | None], None]
"""emit(frame) 或 emit(None) 表关闭。"""


class SSEJournalProjector(JournalProjector):
    """journal → SSE：零翻译，事件类名即 SSE event 字段。"""

    def __init__(self, emit: EmitFn) -> None:
        self._emit = emit

    def on_event(self, stamped: StampedEvent) -> None:
        self._emit(stamped_to_sse_frame(stamped))

    def flush(self) -> None:
        return

    def close(self) -> None:
        self._emit(None)
