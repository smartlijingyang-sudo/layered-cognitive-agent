"""journal.step —— step-tree 落盘投影(ADR-0164 + ADR-0167 D11)。

主存储: ``traces/runs/<run_id>/journal.json``(pretty-printed JSON)。
事件真相: ``traces/runs/<run_id>/<run_id>.spine.jsonl``(SSOT, 单一 append-only)。
两者的关系:
    - SSOT 是 spine ledger
    - journal.json 是由 :class:`StepTreeFoldDeriver` 从事件流 fold
      出来的可重建视图(ADR-0167 I-MV3: Replay ≡ finalize)
    - narrative.md 是 NarrativeDeriver 从同一 events 推导出的另一视图

公开 API:
    JournalDocumentWriter:  JournalDocument → journal.json
    StepGroupedReader:      journal.json → JournalDocument
    read_step_document:     同上的函数形式
    StepNarrativeWriter:    JournalDocument → narrative.md
"""

from lca.infrastructure.observability.journal.step.narrative_writer import (
    StepNarrativeWriter,
)
from lca.infrastructure.observability.journal.step.projector import (
    JournalDocumentWriter,
)
from lca.infrastructure.observability.journal.step.reader import (
    StepGroupedReader,
    read_step_document,
)

__all__ = [
    "JournalDocumentWriter",
    "StepGroupedReader",
    "StepNarrativeWriter",
    "read_step_document",
]
