"""fold_step_tree 纯函数 + StepTreeFoldDeriver facade 单测(PRD-3g 样本)。

覆盖:
- fold_step_tree: 从 dict 事件流 fold 出 JournalDocument
- StepTreeFoldDeriver: derive 写 journal.json + document 可读
- derive_step_tree: 一次性 fold + 写盘
- flush 合并 Session 快照(spine.* 前缀)+ spine ledger(裸 EP),精确重复去重
- run_b2c1424d93d4 真实形态回归锁(journal steps/phases 非空)
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from lca.plugins.session.derivers.step_tree import (
    StepTreeFoldDeriver,
    derive_step_tree,
)
from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree
from lca_kernel.events.session import SessionEvent

# ── fold_step_tree 纯函数 ────────────────────────────────────────


def test_fold_empty_events_returns_empty_document() -> None:
    """空事件流 fold 出 0-step document。"""
    doc = fold_step_tree([], run_id="r_empty")
    assert doc.run_id == "r_empty"
    assert doc.schema == "lca.journal/3.1"
    assert len(doc.steps) == 0
    assert doc.totals is not None
    assert doc.totals.steps == 0


def test_fold_single_step_from_writable_events() -> None:
    """writable.step.start + writable.step.end → 1 step。"""
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "outcome": None,
            "phase": "live",
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "writable.step.end",
            "payload": {"outcome": "success"},
            "outcome": "success",
            "phase": "live",
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r1")
    assert len(doc.steps) == 1
    assert doc.steps[0].phase == "think"
    assert doc.steps[0].outcome == "success"
    assert doc.totals is not None
    assert doc.totals.steps == 1


def test_fold_brain_think_start_end_creates_implicit_step() -> None:
    """brain.think.start/end → 隐式 step(backend ReAct 路径)。"""
    events = [
        {
            "execution_point": "brain.think.start",
            "payload": {},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "brain.think.end",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_implicit")
    assert doc.totals is not None
    assert doc.totals.steps == 1
    assert doc.steps[0].outcome == "success"


def test_fold_phase_fold_creates_phase_record() -> None:
    """phase.think.fold → PhaseRecord(kind='think')。"""
    events = [
        {
            "execution_point": "phase.think.fold",
            "payload": {"summary": "thinking"},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_phase")
    assert doc.totals is not None
    assert doc.totals.phases >= 1
    assert any(p.kind == "think" for p in doc.phases)


def test_fold_model_only_run_keeps_totals_contract() -> None:
    """无 step 事件时:phases 计数,segments 不落 step 则不计数。

    Totals 契约(journal_totals.py):totals.segments ==
    sum(len(s.segments) for s in steps)。declarative model-only run 只有
    phase.*.fold、无 writable.step.*/brain.think.*,旧实现把无主
    think/act fold 也计入 totals.segments → doctor H-seg 断
    (回归:run_6d2d7dee4a7e)。
    """
    events = [
        {
            "execution_point": "phase.perceive.fold",
            "payload": {"summary": ""},
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "phase.think.fold",
            "payload": {"summary": "started"},
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "phase.think.fold",
            "payload": {"summary": "respond"},
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
        {
            "execution_point": "phase.stop.fold",
            "payload": {"summary": ""},
            "when": datetime(2026, 9, 1, 12, 0, 2, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_model_only", outcome="completed")
    assert doc.totals is not None
    assert doc.totals.steps == 0
    assert doc.totals.phases == 4
    assert doc.totals.segments == 0
    assert doc.totals.segments == sum(len(s.segments) for s in doc.steps)


def test_fold_think_fold_with_open_step_counts_segment() -> None:
    """step 打开期间的 think fold → step.segments 与 totals.segments 同步计数。"""
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "phase.think.fold",
            "payload": {"summary": "respond"},
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "writable.step.end",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_seg")
    assert doc.totals is not None
    assert doc.totals.steps == 1
    assert doc.totals.segments == 1
    assert len(doc.steps[0].segments) == 1
    assert doc.totals.segments == sum(len(s.segments) for s in doc.steps)


def test_fold_terminal_outcome_from_kernel_run_stop() -> None:
    """kernel.run.stop outcome=success → metadata.outcome='completed'。"""
    events = [
        {
            "execution_point": "kernel.run.stop",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_term")
    assert doc.metadata.outcome == "completed"


def test_fold_explicit_outcome_overrides_spine() -> None:
    """显式 outcome 参数覆盖 spine 推导。"""
    events = [
        {
            "execution_point": "kernel.run.stop",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_override", outcome="failed")
    assert doc.metadata.outcome == "failed"


def test_fold_tool_call_record_attaches_to_step() -> None:
    """step.tool_call.record flat payload → step.tool_call 非空。"""
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "act"},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "executeCode",
                "invocation_id": "inv_1",
                "arguments": {"code": "print(1)"},
                "arguments_summary": "executeCode(python)",
                "step_index": 1,
            },
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
        {
            "execution_point": "writable.step.end",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 2, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_tool")
    assert len(doc.steps) == 1
    tc = doc.steps[0].tool_call
    assert tc is not None
    assert tc.name == "executeCode"
    assert tc.invocation_id == "inv_1"


def test_fold_skips_unrecognized_events() -> None:
    """未知 EP 被 skip,不中断 fold。"""
    events = [
        {"execution_point": "some.random.ep", "payload": {}, "when": 0.0},
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "writable.step.end",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
    ]
    doc = fold_step_tree(events, run_id="r_skip")
    assert doc.totals is not None
    assert doc.totals.steps == 1


# ── StepTreeFoldDeriver facade ───────────────────────────────────


def test_deriver_writes_journal_json(tmp_path: Path) -> None:
    """derive() 写 journal.json + document 可读。"""
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "execution_point": "writable.step.end",
            "payload": {},
            "outcome": "success",
            "when": datetime(2026, 9, 1, 12, 0, 1, tzinfo=timezone.utc),
        },
    ]
    deriver = StepTreeFoldDeriver(run_id="r_derive", run_dir=tmp_path)
    doc = deriver.derive(events)

    assert (tmp_path / "journal.json").exists()
    assert deriver.document is not None
    assert deriver.document.run_id == "r_derive"
    assert doc.totals is not None
    assert doc.totals.steps == 1


def test_deriver_flush_writes_empty_document(tmp_path: Path) -> None:
    """flush() 无 events 时写空 document。"""
    deriver = StepTreeFoldDeriver(run_id="r_flush", run_dir=tmp_path, outcome="completed")
    deriver.flush()

    assert (tmp_path / "journal.json").exists()
    assert deriver.document is not None
    assert deriver.document.metadata.outcome == "completed"


def test_derive_step_tree_function(tmp_path: Path) -> None:
    """derive_step_tree 一次性函数写 journal.json。"""
    events = [
        {
            "execution_point": "phase.think.fold",
            "payload": {"summary": "thinking"},
            "outcome": None,
            "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]
    doc = derive_step_tree(events, run_id="r_fn", run_dir=tmp_path, outcome="completed")

    journal = json.loads((tmp_path / "journal.json").read_text(encoding="utf-8"))
    assert journal["run_id"] == "r_fn"
    assert journal["schema"] == "lca.journal/3.1"
    assert doc.metadata.outcome == "completed"
    assert doc.totals is not None
    assert doc.totals.phases >= 1


def test_fold_metadata_passthrough() -> None:
    """agent_role / plan_ref / objective 写入 JournalMetadata。"""
    doc = fold_step_tree(
        [],
        run_id="r_meta",
        outcome="completed",
        agent_role="coder",
        strategy_key="solo",
        plan_ref="abcd1234abcd1234",
        objective="ship fold path",
    )
    assert doc.metadata.agent_role == "coder"
    assert doc.metadata.strategy_key == "solo"
    assert doc.metadata.plan_ref == "abcd1234abcd1234"
    assert doc.metadata.objective == "ship fold path"
    assert doc.metadata.outcome == "completed"


def test_fold_iso_when_and_session_event() -> None:
    """ISO when 字符串 + SessionEvent 信封都能 fold 出 step。"""
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "when": "2026-09-01T12:00:00+00:00",
        },
        SessionEvent(
            type="writable.step.end",
            seq=1,
            time=1_756_728_001_000,
            data={"outcome": "success"},
        ),
    ]
    doc = fold_step_tree(events, run_id="r_coerce")
    assert len(doc.steps) == 1
    assert doc.steps[0].outcome == "success"
    assert doc.steps[0].duration_ms is not None
    assert doc.steps[0].duration_ms >= 0


def test_deriver_flush_from_spine_reader(tmp_path: Path) -> None:
    """flush 从 SpineReader 读 spine.jsonl 再 fold 写 journal.json。"""
    run_id = "r_flush_spine"
    spine_path = tmp_path / f"{run_id}.spine.jsonl"
    events = [
        {
            "execution_point": "writable.step.start",
            "payload": {"phase": "think"},
            "outcome": None,
            "when": "2026-09-01T12:00:00+00:00",
        },
        {
            "execution_point": "writable.step.end",
            "payload": {},
            "outcome": "success",
            "when": "2026-09-01T12:00:01+00:00",
        },
    ]
    spine_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    deriver = StepTreeFoldDeriver(
        run_id=run_id,
        run_dir=tmp_path,
        spine_path=spine_path,
        objective="flush from spine",
    )
    deriver.flush(outcome="completed")

    assert (tmp_path / "journal.json").exists()
    assert deriver.document is not None
    assert deriver.document.metadata.outcome == "completed"
    assert deriver.document.metadata.objective == "flush from spine"
    assert deriver.document.totals is not None
    assert deriver.document.totals.steps == 1


def test_deriver_flush_folds_spine_alongside_session_snapshot(tmp_path: Path) -> None:
    """Session 快照含非 fold 词表时,spine ledger 的 step 事件仍被 fold(H-xref 回归锁)。

    生产 run 的 Session log 承载 runtime SSE 词表(无 fold 闭集 EP),
    spine ledger 承载 phase/step 词表;flush 取并集后 fold 必须仍能读
    出 spine 侧的 step,否则 journal totals 恒 0、doctor H-xref 断
    (回归:run_b2c1424d93d4 等 4 连发)。
    """
    from lca.plugins.session.runtime.session import Session

    session = Session("r_spine_first")
    session.append("AgentRunStarted", {"run_id": "r_spine_first"})
    session.append("ReasoningDelta", {"text_delta": "..."})
    spine_path = tmp_path / "r_spine_first.spine.jsonl"
    spine_path.write_text(
        "".join(
            json.dumps(event) + "\n"
            for event in (
                {
                    "execution_point": "writable.step.start",
                    "payload": {"phase": "think"},
                    "when": "2026-09-01T12:00:00+00:00",
                },
                {
                    "execution_point": "writable.step.end",
                    "payload": {},
                    "outcome": "success",
                    "when": "2026-09-01T12:00:01+00:00",
                },
            )
        ),
        encoding="utf-8",
    )
    deriver = StepTreeFoldDeriver(
        run_id="r_spine_first",
        run_dir=tmp_path,
        spine_path=spine_path,
        session=session,
    )
    deriver.flush(outcome="completed")
    assert deriver.document is not None
    assert deriver.document.totals is not None
    assert deriver.document.totals.steps == 1
    assert deriver.document.steps[0].phase == "think"
    assert deriver.document.steps[0].outcome == "success"


def test_deriver_flush_falls_back_to_snapshot_without_spine(tmp_path: Path) -> None:
    """spine 文件缺失时回落 Session.snapshot_events(in-process 路径)。"""
    from lca.plugins.session.runtime.session import Session

    session = Session("r_sess")
    session.append("writable.step.start", {"phase": "act"})
    session.append("writable.step.end", {"outcome": "success"})
    deriver = StepTreeFoldDeriver(
        run_id="r_sess",
        run_dir=tmp_path,
        spine_path=tmp_path / "r_sess.spine.jsonl",
        session=session,
    )
    deriver.flush(outcome="completed")
    assert deriver.document is not None
    assert deriver.document.totals is not None
    assert deriver.document.totals.steps == 1
    assert deriver.document.steps[0].phase == "act"


def test_step_tree_bundle_flush_passes_outcome(tmp_path: Path) -> None:
    """_StepTreeBundle.flush 把 outcome 传给 fold deriver 并写 narrative。"""
    from lca.plugins.observability.run_ledger_seam import _StepTreeBundle

    class _Narrative:
        def __init__(self) -> None:
            self.docs: list[object] = []

        def write(self, document: object) -> None:
            self.docs.append(document)

    spine_path = tmp_path / "r_bundle.spine.jsonl"
    spine_path.write_text(
        json.dumps(
            {
                "execution_point": "kernel.run.stop",
                "payload": {},
                "outcome": "success",
                "when": "2026-09-01T12:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    deriver = StepTreeFoldDeriver(
        run_id="r_bundle",
        run_dir=tmp_path,
        spine_path=spine_path,
    )
    narrative = _Narrative()
    bundle = _StepTreeBundle(deriver=deriver, narrative_writer=narrative)
    bundle.flush(outcome="failed")

    assert (tmp_path / "journal.json").exists()
    assert deriver.document is not None
    assert deriver.document.metadata.outcome == "failed"
    assert narrative.docs == [deriver.document]


# ── Session 快照 + spine ledger 并集 ─────────────────────────────


class _FakeSession:
    """snapshot_events duck-type:固定回归时间戳,不用真实 Session 的 now() 盖章。"""

    def __init__(self, events: Sequence[SessionEvent]) -> None:
        self._events = tuple(events)

    def snapshot_events(self) -> tuple[SessionEvent, ...]:
        return self._events


def test_deriver_flush_merges_session_snapshot_and_spine_with_dedup(tmp_path: Path) -> None:
    """Session 快照(spine.* 前缀)+ spine jsonl(裸 EP)按 epoch 合并;精确重复去重。"""
    run_id = "r_merge"
    session = _FakeSession(
        (
            SessionEvent(
                type="spine.cognition.brain.think.start",
                seq=0,
                time=1_788_512_185_993,
                data={"state_id": "t"},
            ),
            # 与 spine 文件的 phase.think.fold 同源:同 EP + 同时间戳 + 同 payload → 去重
            SessionEvent(
                type="spine.phase.think.fold",
                seq=1,
                time=1_788_512_186_013,
                data={"summary": "respond", "step_index": 1},
            ),
            SessionEvent(
                type="spine.runtime.event_publisher.publish",
                seq=2,
                time=1_788_512_188_973,
                data={"event_type": "completed", "outcome": "success"},
            ),
        )
    )
    spine_path = tmp_path / f"{run_id}.spine.jsonl"
    spine_path.write_text(
        "".join(
            json.dumps(event) + "\n"
            for event in (
                {
                    "execution_point": "phase.think.fold",
                    "payload": {"summary": "respond", "step_index": 1},
                    "when": 1788512186.013,
                },
                {
                    "execution_point": "llm.request.header",
                    "payload": {
                        "step_id": "step-001",
                        "model": "qwen3.7-plus",
                        "reason": "initial",
                    },
                    "when": 1788512186.015,
                },
            )
        ),
        encoding="utf-8",
    )
    deriver = StepTreeFoldDeriver(
        run_id=run_id, run_dir=tmp_path, spine_path=spine_path, session=session
    )
    deriver.flush()

    doc = deriver.document
    assert doc is not None
    assert doc.totals is not None
    # DSH 切步:一步 = 一次模型请求。brain.think.start 开的隐式 think 帧
    # 被 llm.request.header 原地升级(采用 step-001 / model / reason),
    # 不重复计步。
    assert doc.totals.steps == 1
    assert [s.step_id for s in doc.steps] == ["step-001"]
    assert doc.steps[0].outcome == "success"
    # 去重:两流同条 phase.think.fold 只计一次
    assert doc.totals.phases == 1
    assert doc.totals.segments == sum(len(s.segments) for s in doc.steps)
    assert doc.metadata.outcome == "completed"


# ── 回归锁:run_b2c1424d93d4 真实形态 ───────────────────────────


# traces/runs/run_b2c1424d93d4 Session 流(spine.* CATEGORY 前缀 type,epoch 毫秒)。
_RUN_B2C1424D93D4_SESSION: tuple[tuple[str, int, dict[str, object]], ...] = (
    (
        "spine.transport.route.exit",
        1788512185857,
        {"path": "/runs", "method": "POST", "run_id": "", "outcome": "success", "carrier_seq": 3},
    ),
    (
        "spine.kernel.run.start",
        1788512185861,
        {"run_id": "run_b2c1424d93d4", "trace_id": "trace_0af62ccdd1cb"},
    ),
    (
        "spine.agent_loop.iteration.start",
        1788512185904,
        {"trace_id": "trace_0af62ccdd1cb", "role": "助手", "iteration_kind": "fresh"},
    ),
    (
        "spine.runtime.event_publisher.publish",
        1788512185929,
        {"event_type": "started", "trace_id": "trace_0af62ccdd1cb", "outcome": "success"},
    ),
    ("spine.cognition.brain.think.start", 1788512185993, {"state_id": "trace_0af62ccdd1cb"}),
    (
        "spine.cognition.brain.think.end",
        1788512188840,
        {"state_id": "trace_0af62ccdd1cb", "outcome": "success"},
    ),
    (
        "spine.runtime.event_publisher.publish",
        1788512188973,
        {"event_type": "completed", "trace_id": "trace_0af62ccdd1cb", "outcome": "success"},
    ),
    (
        "spine.kernel.run.stop",
        1788512188977,
        {"run_id": "run_b2c1424d93d4", "trace_id": "trace_0af62ccdd1cb", "outcome": "success"},
    ),
)

# traces/runs/run_b2c1424d93d4 spine ledger 的 fold 闭集 EP(裸 EP,ISO when)。
_RUN_B2C1424D93D4_SPINE: tuple[dict[str, object], ...] = (
    {
        "execution_point": "phase.perceive.fold",
        "outcome": None,
        "when": "2026-09-04T08:56:25.989790+00:00",
        "phase": "perceive",
        "payload": {"phase": "perceive", "summary": "", "step_index": 0},
    },
    {
        "execution_point": "phase.think.fold",
        "outcome": None,
        "when": "2026-09-04T08:56:26.013625+00:00",
        "phase": "think",
        "payload": {"phase": "think", "summary": "", "step_index": 0},
    },
    {
        "execution_point": "llm.request.header",
        "outcome": None,
        "when": "2026-09-04T08:56:26.015711+00:00",
        "phase": "think",
        "payload": {
            "step_id": "step-001",
            "incarnation": 1,
            "plan_ref": "70cf2314ccbcd0bf",
            "reason": "initial",
            "model": "qwen3.7-plus",
            "messages_path": "model_visible/step-001/messages.json",
        },
    },
    {
        "execution_point": "phase.think.fold",
        "outcome": None,
        "when": "2026-09-04T08:56:26.015843+00:00",
        "phase": "think",
        "payload": {"phase": "think", "summary": "started", "step_index": 1},
    },
    {
        "execution_point": "phase.think.fold",
        "outcome": None,
        "when": "2026-09-04T08:56:28.835821+00:00",
        "phase": "think",
        "payload": {"phase": "think", "summary": "respond", "step_index": 1},
    },
)


def test_regression_run_b2c1424d93d4_journal_not_empty(tmp_path: Path) -> None:
    """回归锁(run_b2c1424d93d4):Session 前缀事件 + spine 裸 EP 并集 fold 出非空 journal。

    修复前症状:Session 流 type 是 spine.* CATEGORY 前缀,fold 按裸 EP
    匹配 → 零命中 → journal.json steps=[] / phases=[]。
    """
    run_id = "run_b2c1424d93d4"
    session = _FakeSession(
        tuple(
            SessionEvent(type=event_type, seq=seq, time=time_ms, data=data)
            for seq, (event_type, time_ms, data) in enumerate(_RUN_B2C1424D93D4_SESSION)
        )
    )
    spine_path = tmp_path / f"{run_id}.spine.jsonl"
    spine_path.write_text(
        "".join(json.dumps(event) + "\n" for event in _RUN_B2C1424D93D4_SPINE),
        encoding="utf-8",
    )
    deriver = StepTreeFoldDeriver(
        run_id=run_id,
        run_dir=tmp_path,
        spine_path=spine_path,
        session=session,
        objective="用一句话回答:1+1等于几?",
    )
    deriver.flush()

    doc = deriver.document
    assert doc is not None
    assert doc.totals is not None
    assert doc.totals.steps >= 1
    assert doc.totals.phases >= 4
    assert any(step.step_id == "step-001" for step in doc.steps)
    assert doc.metadata.outcome == "completed"

    journal = json.loads((tmp_path / "journal.json").read_text(encoding="utf-8"))
    assert journal["steps"], "journal.json steps 不得为空(回归症状)"
    assert journal["totals"]["steps"] >= 1
    assert journal["totals"]["phases"] >= 4
