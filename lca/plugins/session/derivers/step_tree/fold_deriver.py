"""fold 驱动的 step_tree deriver facade(ADR-0186 PR-3g / ADR-0191 Wave D)。

两条入口:
1. :func:`derive_step_tree` — 一次性函数:传 events + run_id → 写 journal.json。
2. :class:`StepTreeFoldDeriver` — 可复用 facade:持 run_id / run_dir,
   :meth:`derive` 接受 events 迭代器;:meth:`flush` 从 Session 快照或
   spine ledger 单流 fold（不再并集）。

不订阅 EventSpine。:meth:`StepTreeFoldDeriver._iter_events` 规则:
in-process Session 快照非空时仅返回 Session 事件（ADR-0191 SSOT）;
快照为空时仅读 ``<run_id>.spine.jsonl``（offline cold fold）。
# Single-stream fold only (ADR-0191 Wave D / ADR-0192 E4).
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
from lca.plugins.session.derivers.step_tree.journal_fold import (
    fold_step_tree,
)
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
        """fold Session snapshot or spine ledger, write journal.json.

        ``outcome`` overrides the folded terminal state. When no event source
        exists and a prior derive ran, this is a no-op.
        """
        if outcome is not None:
            self._outcome = outcome
        events = list(self._iter_events())
        if not events and self._last_document is not None:
            return
        self.derive(events)

    def _iter_events(self) -> Iterable[Any]:
        """Session in-process SSOT when snapshot exists; spine-only for cold offline fold.

        ADR-0191 Wave D: live run events enter via ``Session.append`` first;
        in-process snapshot is authoritative. Spine ledger supplements only
        when no bound Session snapshot is available (offline doctor/replay).
        """
        session = self._session
        snapshot_events: list[Any] = []
        snapshot = getattr(session, "snapshot_events", None) if session is not None else None
        if callable(snapshot):
            raw_snapshot = snapshot()
            if isinstance(raw_snapshot, Iterable):
                snapshot_events = list(raw_snapshot)

        if snapshot_events:
            return iter(snapshot_events)

        path = self._spine_path
        if path is None:
            path = self._run_dir / f"{self._run_id}.spine.jsonl"
        if path.exists():
            return iter(SpineReader(self._run_id, path=path).read_dicts())
        return iter(())


__all__ = ["StepTreeFoldDeriver", "derive_step_tree"]
