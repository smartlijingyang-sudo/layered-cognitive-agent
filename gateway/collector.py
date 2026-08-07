"""Gateway 专用 ObservabilityHub —— SSE + jsonl 投影，兼容 run_mode 的 bundle() 调用。"""

from __future__ import annotations

from pathlib import Path

from lca.layer0_infra.observability import ObservabilityHub
from lca.layer0_infra.observability.journal.jsonl_projector import JsonlJournalProjector
from lca.layer0_infra.observability.journal.sse_projector import EmitFn, SSEJournalProjector
from lca.layer0_infra.observability.policy import AttributePolicy, Verbosity
from tests.harness.collector import TraceBundle


class GatewayCollector(ObservabilityHub):
    """SSE 广播 + jsonl 落盘；run_mode 收尾会调 bundle()，此处返回空 TraceBundle。"""

    def __init__(self, emit: EmitFn, jsonl_path: Path) -> None:
        super().__init__(
            [],
            policy=AttributePolicy(Verbosity.STANDARD),
            journal_projectors=[
                SSEJournalProjector(emit),
                JsonlJournalProjector(jsonl_path),
            ],
        )

    def bundle(self) -> TraceBundle:
        return TraceBundle()
