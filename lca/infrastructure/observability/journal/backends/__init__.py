"""journal backends —— ADR-0063 PR-8 / ADR-0065 PR-4 引入的存储抽象。

- ``InMemoryJournalStore`` 默认(测试 + boot 期)
- ``FilesystemJournalStore`` ADR-0065 PR-4 落地(L2 durable + atomic append)
"""

from lca.infrastructure.observability.journal.backends.filesystem import FilesystemJournalStore
from lca.infrastructure.observability.journal.backends.memory import InMemoryJournalStore

__all__ = ["FilesystemJournalStore", "InMemoryJournalStore"]
