"""StepTreeAccumulatorDeriver test (ADR-0167 D11 真 SSOT 累积器)。

覆盖:
- ``on_event`` 累积 step_tree_accumulator 接收的 EP
- ``flush`` 写到 ``journal.json``(lca.journal/3.1 schema)
- ``document`` 在 flush 后可读
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.derivers.step_tree_accumulator import (
    StepTreeAccumulatorDeriver,
)
from lca.infrastructure.observability.spine.event_record import EventRecord


def _make_event(**overrides: object) -> EventRecord:
    base: dict[str, object] = {
        "execution_point": "writable.step.start",
        "channel": "control",
        "span_id": "01HM",
        "parent_span_id": None,
        "sequence": 1,
        "epoch": 1,
        "causality_id": "sha256:abc",
        "outcome": None,
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "prev_event_hash": None,
        "run_id": "r1",
        "step_id": "s1",
        "payload": {"phase": "think"},
    }
    base.update(overrides)
    return EventRecord(**base)  # type: ignore[arg-type]


def test_flush_writes_journal_json(tmp_path: Path) -> None:
    """deriver.flush() 写 journal.json + 暴露 document。"""
    SpineContext.set_run("r1")
    run_dir = tmp_path / "r1"
    deriver = StepTreeAccumulatorDeriver(
        run_id="r1",
        run_dir=run_dir,
        agent_role="agt_test",
        strategy_key="solo",
        plan_ref="plan_test",
    )

    # 一个完整 step
    deriver.on_event(_make_event(sequence=1, payload={"phase": "think", "step_id": "step_001"}))
    deriver.on_event(_make_event(
        execution_point="step.thinking.record",
        sequence=2,
        channel="fact",
        payload={"trace": {"model": "x", "latency_ms": 1, "reasoning": "", "decision": "respond"}},
    ))
    deriver.on_event(_make_event(
        execution_point="writable.step.end",
        sequence=3,
        channel="control",
        payload={"step_id": "step_001", "outcome": "success"},
        outcome="success",
    ))

    deriver.flush()

    journal_path = run_dir / "journal.json"
    assert journal_path.exists(), "deriver.flush did not write journal.json"

    doc = deriver.document
    assert doc is not None
    assert doc.run_id == "r1"
    assert doc.schema == "lca.journal/3.1"
    assert len(doc.steps) >= 1
    assert doc.totals.steps >= 1


def test_open_step_at_flush_close_forcibly(tmp_path: Path) -> None:
    """若仍有 step 未 close, flush() 强制以 cancelled 收口。"""
    SpineContext.set_run("r2")
    run_dir = tmp_path / "r2"
    deriver = StepTreeAccumulatorDeriver(
        run_id="r2", run_dir=run_dir, agent_role="agt", strategy_key="solo",
    )
    deriver.on_event(_make_event(
        run_id="r2",
        sequence=1,
        payload={"phase": "act", "step_id": "step_001"},
    ))
    deriver.flush()

    doc = deriver.document
    assert doc is not None
    assert len(doc.steps) == 1
    assert doc.steps[0].outcome in {"cancelled", "fail"}


def test_ignores_other_run_events(tmp_path: Path) -> None:
    """run_id 不匹配的事件被忽略。"""
    SpineContext.set_run("r3")
    run_dir = tmp_path / "r3"
    deriver = StepTreeAccumulatorDeriver(
        run_id="r3", run_dir=run_dir, agent_role="agt", strategy_key="solo",
    )
    deriver.on_event(_make_event(run_id="other-run", sequence=1))
    deriver.flush()

    # 没累积任何 step
    doc = deriver.document
    assert doc is not None
    assert len(doc.steps) == 0
