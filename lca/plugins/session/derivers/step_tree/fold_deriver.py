"""fold 驱动的 step_tree deriver facade(PRD-3g 样本)。

两条入口:
1. :func:`derive_step_tree` — 一次性函数:传 events + run_id → 写 journal.json。
2. :class:`StepTreeFoldDeriver` — 可复用 facade:持 run_id / run_dir,
   :meth:`derive` 接受 events 迭代器,内部调 fold + 写盘。

旧 :class:`StepTreeAccumulatorDeriver` 保留兼容;本模块不替换它,
只提供 fold 纯函数路径。两条路径产出 JournalDocument 语义等价。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal_doc import JournalDocument
from lca.infrastructure.observability.journal.step.projector import (
    JournalDocumentWriter,
)
from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree

log = logging.getLogger(__name__)


def derive_step_tree(
    events: Iterable[Any],
    *,
    run_id: str,
    run_dir: Path,
    outcome: str | None = None,
) -> JournalDocument:
    """一次性 fold + 写盘。

    Parameters:
        events: 事件迭代器(EventRecord / Mapping / SpineEventRecord)。
        run_id: 目标 run 标识。
        run_dir: run 目录;journal.json 写到这里。
        outcome: 显式终态覆盖;None 时由 fold 推导。

    Returns:
        写盘后的 JournalDocument。
    """
    doc = fold_step_tree(events, run_id=run_id, outcome=outcome)
    JournalDocumentWriter(Path(run_dir) / "journal.json").write(doc)
    return doc


class StepTreeFoldDeriver:
    """fold 驱动的 step_tree deriver facade。

    与旧 :class:`StepTreeAccumulatorDeriver` 的接口差异:
    - 不持有 mutable 累积状态;每次 :meth:`derive` 都是独立 fold。
    - 不接受 ``on_event`` 单条订阅(那是旧 callback 路径)。
    - ``document`` 属性只在 ``derive`` 后可读。
    """

    def __init__(
        self,
        run_id: str,
        run_dir: Path,
        *,
        outcome: str | None = None,
    ) -> None:
        self._run_id = run_id
        self._run_dir = Path(run_dir)
        self._outcome = outcome
        self._last_document: JournalDocument | None = None

    @property
    def document(self) -> JournalDocument | None:
        """最后一次 :meth:`derive` 的 JournalDocument。"""
        return self._last_document

    def derive(self, events: Iterable[Any]) -> JournalDocument:
        """从 events 迭代器 fold 出 JournalDocument 并写 journal.json。

        纯 fold:每次调用独立,不续接上次状态。增量 fold 由 caller
        自行拼接 events 前缀。
        """
        doc = fold_step_tree(events, run_id=self._run_id, outcome=self._outcome)
        self._last_document = doc
        try:
            JournalDocumentWriter(self._run_dir / "journal.json").write(doc)
        except Exception as exc:
            log.warning("StepTreeFoldDeriver.derive write failed err=%s", exc)
        return doc

    def flush(self, *, outcome: str | None = None) -> None:
        """兼容旧 deriver 接口:无 events 时仅写空 document。"""
        if outcome is not None:
            self._outcome = outcome
        if self._last_document is not None:
            return
        doc = fold_step_tree([], run_id=self._run_id, outcome=self._outcome)
        self._last_document = doc
        JournalDocumentWriter(self._run_dir / "journal.json").write(doc)


__all__ = ["StepTreeFoldDeriver", "derive_step_tree"]
