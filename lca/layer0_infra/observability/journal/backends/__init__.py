"""journal backends —— ADR-0063 PR-8 引入的存储抽象。

``InMemoryJournalStore`` 是当前唯一实现；文件 backed 是后续 PR（PR-8-ext）
配合 durability ADR 单独落地。
"""

from lca.layer0_infra.observability.journal.backends.memory import InMemoryJournalStore

__all__ = ["InMemoryJournalStore"]
