"""Console projector subscriber —— 把 TEAM_DELEGATION.CACHE_HIT 渲染到 stdout（ADR-0180）。

试点第二个 plugin：证明任何 subscriber 都是 plugin；机制按 yaml 鉴权 + Manifest 声明。
"""

from __future__ import annotations

import sys
from typing import TextIO

from lca.contracts.event import EventPayload
from lca_kernel.events.mechanism import EventRef


class ConsoleProjectorSubscriber:
    """控制台投影 subscriber（plugin 形式）。"""

    def __init__(self, *, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def on_event(self, payload: EventPayload, ref: EventRef) -> None:
        # 试点仅渲染 TEAM_DELEGATION_CACHE_HIT
        if not hasattr(payload, "callee_role"):
            return
        print(
            f"⇢ {payload.callee_role}: 幂等短路（v2 subscriber plugin）",
            file=self._stream,
            flush=True,
        )


__all__ = ["ConsoleProjectorSubscriber"]
