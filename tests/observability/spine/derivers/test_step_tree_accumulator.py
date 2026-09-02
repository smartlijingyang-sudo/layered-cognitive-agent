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
    deriver.on_event(
        _make_event(
            execution_point="step.thinking.record",
            sequence=2,
            channel="fact",
            payload={
                "trace": {"model": "x", "latency_ms": 1, "reasoning": "", "decision": "respond"}
            },
        )
    )
    deriver.on_event(
        _make_event(
            execution_point="writable.step.end",
            sequence=3,
            channel="control",
            payload={"step_id": "step_001", "outcome": "success"},
            outcome="success",
        )
    )

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
        run_id="r2",
        run_dir=run_dir,
        agent_role="agt",
        strategy_key="solo",
    )
    deriver.on_event(
        _make_event(
            run_id="r2",
            sequence=1,
            payload={"phase": "act", "step_id": "step_001"},
        )
    )
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
        run_id="r3",
        run_dir=run_dir,
        agent_role="agt",
        strategy_key="solo",
    )
    deriver.on_event(_make_event(run_id="other-run", sequence=1))
    deriver.flush()

    # 没累积任何 step
    doc = deriver.document
    assert doc is not None
    assert len(doc.steps) == 0


def test_objective_passed_via_constructor(tmp_path: Path) -> None:
    """Regression: deriver 接受 objective kwarg,不再渲染 "(unobserved)"。

    早先 StepTreeAccumulatorDeriver.__init__ 没有 objective 参数,_objective
    永远 = "";_build_document 用 ``self._objective or "(unobserved)"`` 兜底,
    导致 doctor / narrative 里 objective 始终是 "(unobserved)"。
    """
    SpineContext.set_run("r_obj")
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_obj",
        run_dir=tmp_path / "r_obj",
        agent_role="agt",
        strategy_key="solo",
        objective="用户问你好",
    )
    # 至少一个 step 让 flush 走完整路径
    deriver.on_event(
        _make_event(
            run_id="r_obj",
            sequence=1,
            payload={"phase": "think", "step_id": "step_001"},
        )
    )
    deriver.flush(outcome="completed")

    doc = deriver.document
    assert doc is not None
    assert doc.metadata.objective == "用户问你好", (
        f"objective 应来自 constructor,但得到 {doc.metadata.objective!r}"
    )


def test_flush_outcome_overrides_in_progress_default(tmp_path: Path) -> None:
    """Regression: flush(outcome=...) 不再被静默丢弃。

    早先 StepTreeAccumulatorDeriver.flush(self) 不接受参数,materializer 传的
    outcome 被丢弃;_build_document 用 ``completed if _steps else in_progress``,
    0-step run 永远 in_progress → doctor H6 误判。
    """
    SpineContext.set_run("r_out")
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_out",
        run_dir=tmp_path / "r_out",
        agent_role="agt",
        strategy_key="solo",
    )
    # 不发任何 step —— 模拟 model-only respond
    deriver.flush(outcome="completed")

    doc = deriver.document
    assert doc is not None
    assert doc.metadata.outcome == "completed", (
        f"flush(outcome=completed) 应覆盖 in_progress 启发式,但 outcome={doc.metadata.outcome!r}"
    )


def test_terminal_event_captures_completed_outcome(tmp_path: Path) -> None:
    """Regression: spine 上 kernel.run.stop / lifecycle.finally 捕获 terminal outcome。

    materializer.flush 没传 outcome 时,spine 上的 terminal event 仍能让
    journal.metadata.outcome 正确(替代 in_progress)。
    """
    SpineContext.set_run("r_term")
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_term",
        run_dir=tmp_path / "r_term",
        agent_role="agt",
        strategy_key="solo",
    )
    deriver.on_event(
        _make_event(
            run_id="r_term",
            sequence=1,
            execution_point="kernel.run.stop",
            channel="control",
            outcome="success",
            payload={"run_id": "r_term"},
        )
    )
    deriver.flush()  # 不传 outcome —— 靠 spine 捕获

    doc = deriver.document
    assert doc is not None
    assert doc.metadata.outcome == "completed"


def test_event_publisher_completed_event(tmp_path: Path) -> None:
    """Regression: runtime.event_publisher.publish event_type=completed 也算终态。"""
    SpineContext.set_run("r_pub")
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_pub",
        run_dir=tmp_path / "r_pub",
        agent_role="agt",
        strategy_key="solo",
    )
    deriver.on_event(
        _make_event(
            run_id="r_pub",
            sequence=1,
            execution_point="runtime.event_publisher.publish",
            channel="control",
            outcome="success",
            payload={"event_type": "completed", "trace_id": "t"},
        )
    )
    deriver.flush()

    doc = deriver.document
    assert doc is not None
    assert doc.metadata.outcome == "completed"


# ── ADR-0176 D1 regressions ─────────────────────────────


def test_phase_think_fold_creates_phase_record(tmp_path: Path) -> None:
    """ADR-0176 D1 §1 (1):phase.think.fold 必须在 _apply 走 _record_phase 分支。

    早先 PHASE_FOLD_EPS 表里有 phase.think.fold 但 _apply 没用它
    (硬编码 if/elif 漏列),backend ReAct 路径累积空白。
    """
    SpineContext.set_run("r_tfold")
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_tfold",
        run_dir=tmp_path / "r_tfold",
        agent_role="agt",
        strategy_key="solo",
    )
    deriver.on_event(
        _make_event(
            run_id="r_tfold",
            execution_point="phase.think.fold",
            payload={"phase": "think", "summary": "thinking"},
        )
    )
    deriver.flush()

    doc = deriver.document
    assert doc is not None
    assert doc.totals.phases >= 1
    assert any(p.kind == "think" for p in doc.phases)


def test_phase_act_fold_creates_phase_record(tmp_path: Path) -> None:
    """ADR-0176 D1 §1 (1):phase.act.fold 现在也走 _record_phase。"""
    SpineContext.set_run("r_afold")
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_afold",
        run_dir=tmp_path / "r_afold",
        agent_role="agt",
        strategy_key="solo",
    )
    deriver.on_event(
        _make_event(
            run_id="r_afold",
            execution_point="phase.act.fold",
            payload={"phase": "act", "summary": "acting"},
        )
    )
    deriver.flush()

    doc = deriver.document
    assert doc is not None
    assert doc.totals.phases >= 1
    assert any(p.kind == "act" for p in doc.phases)


def test_brain_think_start_end_implicit_step_envelope(tmp_path: Path) -> None:
    """ADR-0176 D1 §1 (2):backend ReAct 路径不发 writable.step.* 但发
    brain.think.start/end → 隐式 begin_step/close_step。

    显式 writable.step.start/end 优先(不变);brain.think.start 仅为
    fallback 兜底。
    """
    SpineContext.set_run("r_env")
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_env",
        run_dir=tmp_path / "r_env",
        agent_role="agt",
        strategy_key="solo",
    )
    deriver.on_event(
        _make_event(
            run_id="r_env",
            execution_point="brain.think.start",
            payload={"state_id": "abc"},
        )
    )
    deriver.on_event(
        _make_event(
            run_id="r_env",
            execution_point="llm.call.end",
            payload={
                "model": "m",
                "latency_ms": 10,
                "decision": "respond",
            },
        )
    )
    deriver.on_event(
        _make_event(
            run_id="r_env",
            execution_point="brain.think.end",
            outcome="success",
            payload={"state_id": "abc"},
        )
    )
    deriver.flush(outcome="completed")

    doc = deriver.document
    assert doc is not None
    assert doc.totals.steps == 1, (
        f"brain.think.start/end 应隐式开闭 step,得到 {doc.totals.steps}"
    )
    assert doc.steps[0].outcome == "success"


def test_brain_think_does_not_nest_explicit_step(tmp_path: Path) -> None:
    """ADR-0176 D1 §1 (2):显式 writable.step.* 优先级 > 隐式 brain.think.*。

    writable.step.start 后再发 brain.think.start 不应嵌套开第二个 step。
    """
    SpineContext.set_run("r_expl")
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_expl",
        run_dir=tmp_path / "r_expl",
        agent_role="agt",
        strategy_key="solo",
    )
    deriver.on_event(
        _make_event(
            run_id="r_expl",
            execution_point="writable.step.start",
            payload={"phase": "think", "step_id": "step_001"},
        )
    )
    # brain.think.start 不应再开新 step
    deriver.on_event(
        _make_event(
            run_id="r_expl",
            execution_point="brain.think.start",
            payload={"state_id": "x"},
        )
    )
    deriver.on_event(
        _make_event(
            run_id="r_expl",
            execution_point="writable.step.end",
            payload={"step_id": "step_001", "outcome": "success"},
            outcome="success",
        )
    )
    deriver.flush()

    doc = deriver.document
    assert doc is not None
    assert doc.totals.steps == 1


def test_empty_flush_writes_flush_error_to_manifest(tmp_path: Path) -> None:
    """ADR-0176 D1 §1 (3):空累积 → manifest.extra.flush_errors 写入。

    0-step + 0-phase + 已完成 run → 仍写 journal.json(空 doc),但 manifest
    标 flush_errors,让 doctor H-xref 报 broken。
    """
    SpineContext.set_run("r_empty")
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_empty",
        run_dir=tmp_path / "r_empty",
        agent_role="agt",
        strategy_key="solo",
    )
    deriver.flush(outcome="completed")

    manifest_path = tmp_path / "r_empty" / "manifest.json"
    assert manifest_path.exists(), "空累积应写 manifest.json"

    import json as _json

    data = _json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = data.get("extra", {}).get("flush_errors", [])
    assert errors, "空累积应在 manifest.extra.flush_errors 留记录"
    assert any(e.get("operation") == "step_tree.flush.empty" for e in errors)


def test_non_empty_flush_does_not_write_flush_error(tmp_path: Path) -> None:
    """ADR-0176 D1 §1 (3):正常累积不写 flush_errors。"""
    SpineContext.set_run("r_ne")
    deriver = StepTreeAccumulatorDeriver(
        run_id="r_ne",
        run_dir=tmp_path / "r_ne",
        agent_role="agt",
        strategy_key="solo",
    )
    deriver.on_event(
        _make_event(
            run_id="r_ne",
            execution_point="brain.think.start",
            payload={"state_id": "abc"},
        )
    )
    deriver.on_event(
        _make_event(
            run_id="r_ne",
            execution_point="brain.think.end",
            outcome="success",
            payload={"state_id": "abc"},
        )
    )
    deriver.flush(outcome="completed")

    manifest_path = tmp_path / "r_ne" / "manifest.json"
    if manifest_path.exists():
        import json as _json

        data = _json.loads(manifest_path.read_text(encoding="utf-8"))
        errors = data.get("extra", {}).get("flush_errors", [])
        assert not errors, f"正常累积不应写 flush_errors,但得到 {errors}"
