"""Journal store backends —— ``JournalStoreBackend`` 协议的两个实现。

- ``InMemoryJournalStore``: 进程内唯一当前生产实现(boot 期 + 测试)。
- ``FilesystemJournalStore``: append-only 落盘后端,被 ``run_ledger`` seam
  用作 spine 事件的 durable backing store。
"""

from lca.infrastructure.observability.journal.backends.filesystem import FilesystemJournalStore
from lca.infrastructure.observability.journal.backends.memory import InMemoryJournalStore

__all__ = ["FilesystemJournalStore", "InMemoryJournalStore"]
