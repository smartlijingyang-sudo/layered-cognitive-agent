"""jsonl subpackage —— ADR-0164 Phase 7 已删除。

原 ``JsonlJournalProjector`` 已被 ``StepGroupedProjector`` 取代:
- 旧 ``journal.jsonl`` (v2 stream envelope) 不再由 boot 生成
- 旧 run 的 ``journal.jsonl`` 保留为 ``journal.raw.jsonl`` (回放兜底)
- ``lca-ops journal migrate`` 启发式重建为 step-tree

如需读历史 jsonl: ``journal_io.load_journal_records`` 仍在
``lca.infrastructure.observability.journal.engine.journal_io`` 提供。
"""
