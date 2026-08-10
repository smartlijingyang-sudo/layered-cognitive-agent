"""SSEJournalProjector —— journal → SSE 广播投影器（与 console/jsonl 平级）。

消费盖章事件，经 ``stamped_to_sse_frame`` 产出标准 SSE 帧，交给注入的
``emit`` 回调（网关 RunSession 广播给多订阅者）。队列满时丢弃非关键
``RunInsight`` 事件，避免慢消费者拖垮生产者。
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import RunInsight, StampedEvent, StepTextDelta
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.observability.journal.sse_frames import stamped_to_sse_frame

EmitFn = Callable[[str | None], None]
"""emit(frame) 或 emit(None) 表关闭。"""

_DEFAULT_MAX_PENDING = 512
"""emit 回调内部队列建议上限（RunSession 侧 enforce）。"""


class SSEJournalProjector(JournalProjector):
    """journal → SSE：零翻译，事件类名即 SSE event 字段。"""

    def __init__(self, emit: EmitFn) -> None:
        self._emit = emit

    def on_event(self, stamped: StampedEvent) -> None:
        if isinstance(stamped.event, RunInsight):
            # RunInsight 可丢弃：InsightEngine 回注，非协作叙事关键路径
            with contextlib.suppress(Exception):
                self._emit(stamped_to_sse_frame(stamped))
            return
        # 过滤 decision channel 的 StepTextDelta — 只转发 answer channel
        if (
            isinstance(stamped.event, StepTextDelta)
            and stamped.event.channel == StreamChannel.DECISION.value
        ):
            return
        self._emit(stamped_to_sse_frame(stamped))

    def flush(self) -> None:
        return

    def close(self) -> None:
        self._emit(None)
