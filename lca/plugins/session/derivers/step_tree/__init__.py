"""step_tree fold deriver — fold 驱动的 JournalDocument 派生(ADR-0186 PR-3g)。

生产路径用纯 :func:`fold_step_tree` 从 ``Session.snapshot_events`` 或
``SpineReader`` 拉事件流,一次性 fold 出 ``JournalDocument``,再经
``JournalDocumentWriter`` 写 journal.json。

职责:
- 读事件(Session 快照 / SpineReader / caller 直接传的 events)
- fold(fold_step_tree 纯函数)
- 写盘(JournalDocumentWriter)

不订阅 EventSpine、不持有跨 flush 的累积 state、不跑 LLM。
"""

from lca.plugins.session.derivers.step_tree.fold_deriver import (
    StepTreeFoldDeriver,
    derive_step_tree,
)

__all__ = ["StepTreeFoldDeriver", "derive_step_tree"]
