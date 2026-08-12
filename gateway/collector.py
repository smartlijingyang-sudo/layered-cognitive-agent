"""Gateway 专用 ObservabilityHub —— EventBus + jsonl 双投影。

Refactored: SSE 广播从字符串帧（SSEJournalProjector）升级为类型化事件总线
（EventBusProjector + EventBus）。JSONL 落盘保持不变。
"""

from __future__ import annotations

from pathlib import Path

from gateway.events import EventBus, EventBusProjector
from lca.layer0_infra.observability import ObservabilityHub
from lca.layer0_infra.observability.journal.jsonl_projector import JsonlJournalProjector
from lca.layer0_infra.observability.policy import AttributePolicy, Verbosity
from lca.layer0_infra.observability.settings import ObservabilitySettings


class GatewayCollector(ObservabilityHub):
    """EventBus 广播 + jsonl 落盘，作为 Team/Agent 的可观测性后端。"""

    def __init__(
        self,
        bus: EventBus,
        jsonl_path: Path,
        *,
        verbosity: Verbosity | None = None,
    ) -> None:
        resolved = verbosity if verbosity is not None else ObservabilitySettings().verbosity
        super().__init__(
            [],
            policy=AttributePolicy(resolved),
            journal_projectors=[
                EventBusProjector(bus),
                JsonlJournalProjector(jsonl_path),
            ],
        )
