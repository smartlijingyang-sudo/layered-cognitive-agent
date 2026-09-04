"""fold 驱动的 step_tree deriver facade(ADR-0186 PR-3g 生产路径)。

两条入口:
1. :func:`derive_step_tree` — 一次性函数:传 events + run_id → 写 journal.json。
2. :class:`StepTreeFoldDeriver` — 可复用 facade:持 run_id / run_dir,
   :meth:`derive` 接受 events 迭代器;:meth:`flush` 从 Session 快照或
   SpineReader 拉事件再 fold。

不订阅 EventSpine。事件源优先级:
``SpineReader.read_dicts()``(spine ledger)→ ``session.snapshot_events()``
兜底;理由与删除条件见 :meth:`StepTreeFoldDeriver._iter_events` 的 COMPAT 块。
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
from lca_kernel.events.reader import SpineReader

log = logging.getLogger(__name__)


def derive_step_tree(
    events: Iterable[Any],
    *,
    run_id: str,
    run_dir: Path,
    outcome: str | None = None,
    agent_role: str = "",
    strategy_key: str = "",
    plan_ref: str = "",
    objective: str = "",
) -> JournalDocument:
    """一次性 fold + 写盘。

    Parameters:
        events: 事件迭代器(EventRecord / SessionEvent / Mapping / SpineEventRecord)。
        run_id: 目标 run 标识。
        run_dir: run 目录;journal.json 写到这里。
        outcome: 显式终态覆盖;None 时由 fold 推导。
        agent_role / strategy_key / plan_ref / objective: 写入 JournalMetadata。

    Returns:
        写盘后的 JournalDocument。
    """
    doc = fold_step_tree(
        events,
        run_id=run_id,
        outcome=outcome,
        agent_role=agent_role,
        strategy_key=strategy_key,
        plan_ref=plan_ref,
        objective=objective,
    )
    JournalDocumentWriter(Path(run_dir) / "journal.json").write(doc)
    return doc


class StepTreeFoldDeriver:
    """fold 驱动的 step_tree deriver facade。

    与 :class:`StepTreeAccumulatorDeriver` 的接口差异:
    - 不持有 mutable 累积状态;每次 :meth:`derive` / :meth:`flush` 都是独立 fold。
    - 不接受 ``on_event`` 单条订阅(那是旧 callback 路径)。
    - ``document`` 属性只在 ``derive`` / ``flush`` 后可读。
    """

    def __init__(
        self,
        run_id: str,
        run_dir: Path,
        *,
        outcome: str | None = None,
        spine_path: Path | None = None,
        session: Any | None = None,
        agent_role: str = "",
        strategy_key: str = "",
        plan_ref: str = "",
        objective: str = "",
    ) -> None:
        self._run_id = run_id
        self._run_dir = Path(run_dir)
        self._outcome = outcome
        self._spine_path = Path(spine_path) if spine_path is not None else None
        self._session = session
        self._agent_role = agent_role
        self._strategy_key = strategy_key
        self._plan_ref = plan_ref
        self._objective = objective
        self._last_document: JournalDocument | None = None

    @property
    def document(self) -> JournalDocument | None:
        """最后一次 :meth:`derive` / :meth:`flush` 的 JournalDocument。"""
        return self._last_document

    def derive(self, events: Iterable[Any]) -> JournalDocument:
        """从 events 迭代器 fold 出 JournalDocument 并写 journal.json。

        纯 fold:每次调用独立,不续接上次状态。增量 fold 由 caller
        自行拼接 events 前缀。
        """
        doc = fold_step_tree(
            events,
            run_id=self._run_id,
            outcome=self._outcome,
            agent_role=self._agent_role,
            strategy_key=self._strategy_key,
            plan_ref=self._plan_ref,
            objective=self._objective,
        )
        self._last_document = doc
        try:
            JournalDocumentWriter(self._run_dir / "journal.json").write(doc)
        except Exception as exc:
            log.warning("StepTreeFoldDeriver.derive write failed err=%s", exc)
        return doc

    def flush(self, *, outcome: str | None = None) -> None:
        """从 spine ledger(缺省/空时回落 Session 快照)fold 并写 journal.json。

        ``outcome`` 覆盖 fold 推导的终态。无事件源且尚未 derive 时写空 document。
        """
        if outcome is not None:
            self._outcome = outcome
        events = list(self._iter_events())
        if not events and self._last_document is not None:
            return
        self.derive(events)

    def _iter_events(self) -> Iterable[Any]:
        """事件源:spine ledger 第一,缺失/空时回落 Session.snapshot_events。

        # COMPAT(delete-when: ADR-0186 §5 producer 迁移完成 —— spine 词表事件
        # 全部经 Session.append 进 in-process log、snapshot 含 phase.*.fold 等
        # fold 闭集 EP(验证:对任一 completed run 的 snapshot fold 出
        # totals.phases > 0),tracking: ADR-0186)

        fold 消费 spine 词表闭集(:data:`PHASE_FOLD_EPS` / ``writable.*`` /
        ``llm.call.*`` …)。迁移完成前,Session log 只承载 runtime SSE 词表
        (``AgentRunStarted`` / ``ReasoningDelta`` …),feed 给 fold 全部 skip →
        journal totals 恒 0 → doctor H-xref 断。spine ledger 是当前唯一承载
        fold 词表的事件流,故为第一事件源;文件缺失或空时回落 snapshot,
        保留无 spine 文件的 in-process 路径。
        """
        path = self._spine_path
        if path is None:
            path = self._run_dir / f"{self._run_id}.spine.jsonl"
        if path.exists():
            spine_events = list(SpineReader(self._run_id, path=path).read_dicts())
            if spine_events:
                return iter(spine_events)
        session = self._session
        snapshot = getattr(session, "snapshot_events", None) if session is not None else None
        if callable(snapshot):
            snapshot_events = snapshot()
            if isinstance(snapshot_events, Iterable):
                return snapshot_events
        return iter(())


__all__ = ["StepTreeFoldDeriver", "derive_step_tree"]
