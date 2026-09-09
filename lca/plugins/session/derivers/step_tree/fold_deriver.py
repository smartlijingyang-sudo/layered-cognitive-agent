"""fold 驱动的 step_tree deriver facade(ADR-0186 PR-3g / ADR-0191 Wave D / ADR-0212)。

两条入口:
1. :func:`derive_step_tree` — 一次性函数:传 events + run_id → 写 journal.json。
2. :class:`StepTreeFoldDeriver` — 可复用 facade:持 run_id / run_dir,
   :meth:`derive` 接受 events 迭代器;:meth:`flush` 从 Session 快照或
   spine ledger 单流 fold（不再并集）。

不订阅 EventSpine。:meth:`StepTreeFoldDeriver._iter_events` 规则:
in-process Session 快照非空时仅返回 Session 事件（ADR-0191 SSOT）;
快照为空时仅读 ``<run_id>.spine.jsonl``（offline cold fold）。
# Single-stream fold only (ADR-0191 Wave D / ADR-0192 E4).
# ADR-0212 §5:写盘失败 fail-loud → JournalWriteError;不再 log.warning + swallow。
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal.doc import JournalDocument
from lca.contracts.observability.journal.errors import JournalWriteError
from lca.infrastructure.observability.journal.step.projector import (
    JournalDocumentWriter,
)
from lca.plugins.session.derivers.step_tree.journal_fold import (
    fold_step_tree,
)
from lca_kernel.events.reader.reader import SpineReader


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

    Raises:
        JournalWriteError: 写盘失败(ADR-0212 §5)。观测面失败 = 事实面事件,
            必须 raise,不再 silent failure 留下 stale journal.json。
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
    target = Path(run_dir) / "journal.json"
    try:
        JournalDocumentWriter(target).write(doc)
    except Exception as exc:
        raise JournalWriteError(run_id, target, exc) from exc
    return doc


class StepTreeFoldDeriver:
    """fold 驱动的 step_tree deriver facade —— journal.json 派生面唯一真值(ADR-0212)。

    - 不持有 mutable 累积状态;每次 :meth:`derive` / :meth:`flush` 都是独立 fold。
    - 不订阅 EventSpine;只从 Session snapshot 或 spine ledger 单流 fold。
    - 写盘失败 fail-loud:抛 :class:`JournalWriteError`(ADR-0212 §5)。
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

        写盘失败 raise :class:`JournalWriteError`(ADR-0212 §5):观测面失败
        = 事实面事件,不再 ``log.warning + swallow``。幂等性由 fold 的纯函数
        语义保证:同 events 输入永远产同 ``JournalDocument``。
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
        target = self._run_dir / "journal.json"
        try:
            JournalDocumentWriter(target).write(doc)
        except Exception as exc:
            raise JournalWriteError(self._run_id, target, exc) from exc
        return doc

    def flush(self, *, outcome: str | None = None) -> None:
        """fold Session snapshot or spine ledger, write journal.json。

        ``outcome`` overrides the folded terminal state. When no event source
        exists and a prior derive ran, this is a no-op.

        写盘失败 raise :class:`JournalWriteError`(ADR-0212 §5):fail-loud
        同 :meth:`derive`。幂等性:同 events 同 outcome 重复调用产出同
        JournalDocument,写盘覆盖同一份文件,step 数量与 step_id 集合不变。
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
