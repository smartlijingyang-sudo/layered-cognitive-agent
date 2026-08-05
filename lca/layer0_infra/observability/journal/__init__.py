"""journal 子包 —— 执行日志引擎（ADR-0037）。

包内模块仅供 observability 包根装配；外部一律经包根 ``__init__`` 使用
（边界守卫强制）。投影器实现（otel/console/jsonl/sequence/insight）
按分阶段路线陆续加入。
"""

from lca.layer0_infra.observability.journal.engine import (
    ExecutionJournal,
    UnregisteredJournalEventError,
)
from lca.layer0_infra.observability.journal.otel_projector import OtelProjector

__all__ = [
    "ExecutionJournal",
    "OtelProjector",
    "UnregisteredJournalEventError",
]
