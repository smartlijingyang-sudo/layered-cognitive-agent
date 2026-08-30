"""journal 子包 —— RunStore + 派生面（ADR-0055）。

包内模块按职责拆分为子包：

- engine/      RunStore, ProcessJournal, Reducer, 序列化与 IO
- enrichment/  EventEnrichers
- otel/        OtelProjector + OTel mapping + span index
- console/     ConsoleProjector + sequence diagram + table renderer
- jsonl/       JsonlProjector
- sse/         SSE frames
- stream/      LiveTail + FactStream + NarrativeSidecar
- backends/    Filesystem + InMemory journal stores

外部一律经本 ``__init__`` 使用公共入口（边界守卫强制）。
"""

from lca.infrastructure.observability.journal.engine.engine import (
    RunStore,
    UnregisteredJournalEventError,
)
from lca.infrastructure.observability.journal.engine.reducer import (
    RunState,
    RunStatus,
    fold_run_state,
)
from lca.infrastructure.observability.journal.otel.projector import OtelProjector

__all__ = [
    "OtelProjector",
    "RunState",
    "RunStatus",
    "RunStore",
    "UnregisteredJournalEventError",
    "fold_run_state",
]
