"""journal 子包 —— RunStore + 派生面（ADR-0055）。

包内模块仅供 observability 包根装配；外部一律经包根 ``__init__`` 使用
（边界守卫强制）。subscriber 实现（otel/console/jsonl/sequence/insight/reducer）
在此子包内。
"""

from lca.infrastructure.observability.journal.engine import (
    RunStore,
    UnregisteredJournalEventError,
)
from lca.infrastructure.observability.journal.otel_projector import OtelProjector
from lca.infrastructure.observability.journal.reducer import (
    RunState,
    RunStatus,
    fold_run_state,
)

__all__ = [
    "OtelProjector",
    "RunState",
    "RunStatus",
    "RunStore",
    "UnregisteredJournalEventError",
    "fold_run_state",
]
