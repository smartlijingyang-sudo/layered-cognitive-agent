"""Gateway 专用 ObservabilityHub —— SSE + jsonl 双投影。"""

from __future__ import annotations

from pathlib import Path

from lca.layer0_infra.observability import ObservabilityHub
from lca.layer0_infra.observability.journal.jsonl_projector import JsonlJournalProjector
from lca.layer0_infra.observability.journal.sse_projector import EmitFn, SSEJournalProjector
from lca.layer0_infra.observability.policy import AttributePolicy, Verbosity
from lca.layer0_infra.observability.settings import ObservabilitySettings


class GatewayCollector(ObservabilityHub):
    """SSE 广播 + jsonl 落盘，作为 Team/Agent 的可观测性后端。"""

    def __init__(
        self, emit: EmitFn, jsonl_path: Path, *, verbosity: Verbosity | None = None
    ) -> None:
        resolved = verbosity if verbosity is not None else ObservabilitySettings().verbosity
        super().__init__(
            [],
            policy=AttributePolicy(resolved),
            journal_projectors=[
                SSEJournalProjector(emit),
                JsonlJournalProjector(jsonl_path),
            ],
        )
