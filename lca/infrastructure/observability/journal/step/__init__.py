"""journal.step —— step-tree 落盘投影(ADR-0164 草案 Phase 2 + 4)。

主存储: ``traces/runs/<run_id>/journal.json``(pretty-printed JSON)。
顶层真相是 step 树, 不是 seq 流水。 与 ``journal.jsonl``(v2 流式)
不共存 —— 主路径走这里。

公开 API:
    StepGroupedProjector:    接收 JournalDocument, 一次性写 journal.json
    StepGroupedReader:       从 journal.json 还原为 JournalDocument
    StepGroupedBackend:      JournalBackend 包装, 让 boot 装配挂到 BoundObservability
    StepNarrativeWriter:     JournalDocument → narrative.md(替换 NarrativeSidecar)
"""

from lca.infrastructure.observability.journal.step.backend import (
    StepGroupedBackend,
)
from lca.infrastructure.observability.journal.step.narrative_writer import (
    StepNarrativeWriter,
)
from lca.infrastructure.observability.journal.step.projector import (
    StepGroupedProjector,
)
from lca.infrastructure.observability.journal.step.reader import (
    StepGroupedReader,
    read_step_document,
)

__all__ = [
    "StepGroupedBackend",
    "StepGroupedProjector",
    "StepGroupedReader",
    "StepNarrativeWriter",
    "read_step_document",
]
