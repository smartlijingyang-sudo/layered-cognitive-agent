"""fold 驱动的 step_tree deriver facade(ADR-0186 PR-3g 生产路径)。

两条入口:
1. :func:`derive_step_tree` — 一次性函数:传 events + run_id → 写 journal.json。
2. :class:`StepTreeFoldDeriver` — 可复用 facade:持 run_id / run_dir,
   :meth:`derive` 接受 events 迭代器;:meth:`flush` 取 Session 快照与
   spine ledger 的事件并集再 fold。

不订阅 EventSpine。:meth:`StepTreeFoldDeriver._iter_events` 合并两路事件源:
Session 快照承载认知遥测(``spine.*`` CATEGORY 前缀 type),
``<run_id>.spine.jsonl`` 承载 cursor EP(``phase.*.fold`` /
``llm.request.header`` / ``step.*.record``),journal 需要两者的并集。
合并按 epoch 秒稳定排序(同刻 session 在前),精确重复去重;
删除条件见 ``_iter_events`` 的 COMPAT 块。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal_doc import JournalDocument
from lca.infrastructure.observability.journal.step.projector import (
    JournalDocumentWriter,
)
from lca.plugins.session.derivers.step_tree.journal_fold import (
    _coerce,
    _epoch_seconds,
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


def _event_epoch(event: Any) -> float:
    """合并排序键:原始事件 → Unix epoch 秒;无法解析记 0.0。"""
    coerced = _coerce(event)
    if coerced is None:
        return 0.0
    for key in ("when", "ts", "time"):
        parsed = _epoch_seconds(coerced.get(key))
        if parsed is not None:
            return parsed
    return 0.0


def _dedup_key(event: Any) -> tuple[str, float, str] | None:
    """精确重复判定键:(归一 EP, epoch 秒, payload 规范形)。

    Session 形态 type 经 fold 的 CATEGORY 反查归一为裸 EP 后参与比较,
    跨流同源事件才会撞键。不可归一的事件返回 None,不参与去重。
    """
    coerced = _coerce(event)
    if coerced is None:
        return None
    payload = coerced.get("payload")
    if not isinstance(payload, Mapping):
        payload = {}
    try:
        payload_repr = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        payload_repr = repr(payload)
    return (str(coerced.get("execution_point") or ""), _event_epoch(event), payload_repr)


def _merge_events(session_events: Sequence[Any], spine_events: Sequence[Any]) -> list[Any]:
    """并集两路事件流:按 epoch 秒稳定排序(同刻 session 在前),精确重复去重。"""
    ordered = sorted([*session_events, *spine_events], key=_event_epoch)
    seen: set[tuple[str, float, str]] = set()
    merged: list[Any] = []
    for event in ordered:
        key = _dedup_key(event)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        merged.append(event)
    return merged


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
        """fold Session 快照与 spine ledger 的事件并集,写 journal.json。

        ``outcome`` 覆盖 fold 推导的终态。无事件源且尚未 derive 时写空 document。
        """
        if outcome is not None:
            self._outcome = outcome
        events = list(self._iter_events())
        if not events and self._last_document is not None:
            return
        self.derive(events)

    def _iter_events(self) -> Iterable[Any]:
        """事件源并集:Session.snapshot_events + spine ledger。

        # COMPAT(delete-when: PR-3h Session append hook 生产接线、spine EP 与 Session 收敛为单流(rg 两文件事件集相同),
        #   tracking: docs/notes/proposed/seam/2026-09-03-observation-convergence-root.md)

        ADR-0186 迁移期两路事件流互补:认知遥测(``spine.*`` CATEGORY 前缀
        type)在 Session 流,cursor EP(``phase.*.fold`` / ``llm.request.header``
        / ``step.*.record``)只在 ``<run_id>.spine.jsonl`` —— journal 需要
        并集。合并按 epoch 秒排序,同刻 session 事件在前;精确重复
        (同 EP + 同时间戳 + 同 payload)去重,防单流收敛后双计。
        无 session 时仅读 spine 文件;两者皆空返回空迭代器。
        """
        session = self._session
        snapshot_events: list[Any] = []
        snapshot = getattr(session, "snapshot_events", None) if session is not None else None
        if callable(snapshot):
            raw_snapshot = snapshot()
            if isinstance(raw_snapshot, Iterable):
                snapshot_events = list(raw_snapshot)

        path = self._spine_path
        if path is None:
            path = self._run_dir / f"{self._run_id}.spine.jsonl"
        spine_events: list[Any] = []
        if path.exists():
            spine_events = list(SpineReader(self._run_id, path=path).read_dicts())

        if not snapshot_events:
            return iter(spine_events)
        if not spine_events:
            return iter(snapshot_events)
        return iter(_merge_events(snapshot_events, spine_events))


__all__ = ["StepTreeFoldDeriver", "derive_step_tree"]
