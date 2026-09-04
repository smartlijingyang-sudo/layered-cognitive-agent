"""step_tree fold deriver — fold 驱动的 JournalDocument 派生(PRD-3g 样本)。

旧 :class:`StepTreeAccumulatorDeriver` 走 in-memory callback 累积;本模块
用纯 :func:`fold_step_tree` 从 ``SpineReader`` 拉事件流,一次性 fold 出
``JournalDocument``,再经 ``JournalDocumentWriter`` 写 journal.json。

职责:
- 读事件(SpineReader 或 caller 直接传的 events)
- fold(fold_step_tree 纯函数)
- 写盘(JournalDocumentWriter)

不订阅 spine、不持有 mutable state、不跑 LLM。
"""

from lca.plugins.session.derivers.step_tree.fold_deriver import (
    StepTreeFoldDeriver,
    derive_step_tree,
)

__all__ = ["StepTreeFoldDeriver", "derive_step_tree"]
