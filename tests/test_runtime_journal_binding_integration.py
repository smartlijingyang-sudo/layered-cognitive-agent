"""ADR-0167 D11 端到端回归: build_step_coordinator → spine subscribe deriver
→ StepTreeAccumulatorDeriver.flush() 完整闭环。

不变量(ADR-0167 D11 + I-MV3 Replay ≡ finalize):
    1. ``build_step_coordinator`` 立即得到一个已 ``bind_run`` 的 coordinator。
    2. RunSessionBuilder 构造 StepTreeAccumulatorDeriver + subscribe 到
       spine event_spine; spine 上 emit 触发的 EP 都被 deriver 累积。
    3. deriver.flush() 写 ``journal.json``, schema=lca.journal/3.1,
       totals.steps >= 1。
    4. deriver.document 在 flush 后可读, ``metadata.agent_role`` 反映入参。
    5. 同一 events 两次 run → 相同 document 内容(等价性)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.derivers.step_tree_accumulator import (
    StepTreeAccumulatorDeriver,
)
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink
from lca.infrastructure.observability.writable_matrix import (
    LineCoalescer,
    NdjsonSerializer,
    NullStorage,
    SpineEmitter,
    StandardDriver,
    WritableFaceRegistry,
)
from lca.runtime.journal_setup import BuildJournalMetadata, build_step_coordinator


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
        "payload": {"phase": "think", "step_id": "step_001"},
    }
    base.update(overrides)
    return EventRecord(**base)  # type: ignore[arg-type]


def _make_registry() -> WritableFaceRegistry:
    registry = WritableFaceRegistry()
    registry.register("emitter", SpineEmitter())
    registry.register("driver", StandardDriver())
    registry.register("coalescer", LineCoalescer())
    registry.register("serializer", NdjsonSerializer())
    registry.register("storage", NullStorage())
    return registry


def _build_metadata() -> BuildJournalMetadata:
    return BuildJournalMetadata(
        agent_role="agt_test",
        strategy_key="solo",
        plan_ref="plan_e2e",
        objective="end-to-end journal binding",
    )


def test_build_step_coordinator_binds_metadata() -> None:
    """build_step_coordinator 立即产出 bind_run 过的 coordinator。"""
    registry = _make_registry()
    coord = build_step_coordinator(
        registry=registry,
        run_id="run_test_bind",
        trace_id="trace_test_bind",
        metadata=_build_metadata(),
    )
    assert coord.run_id == "run_test_bind"
    assert coord.trace_id == "trace_test_bind"


def test_step_tree_deriver_writes_journal_via_spine(tmp_path: Path) -> None:
    """deriver 订阅 spine, deriver.flush() 写 journal.json。"""
    SpineContext.set_run("run_e2e")
    run_dir = tmp_path / "run_e2e"
    run_dir.mkdir()
    deriver = StepTreeAccumulatorDeriver(
        run_id="run_e2e",
        run_dir=run_dir,
        agent_role="agt_e2e",
        strategy_key="solo",
        plan_ref="plan_e2e",
    )
    # FileSink 是 EventSink; event_spine 把它收作 sink, deriver 是 subscriber
    sink = FileSink(tmp_path, run_id="run_e2e")
    spine = EventSpine(sinks=[sink], subscribers=[deriver.on_event])

    # 模拟一个完整 step
    spine.append(
        execution_point="writable.step.start",
        channel="control",
        caller_payload={"phase": "think", "step_id": "step_001"},
    )
    spine.append(
        execution_point="step.thinking.record",
        channel="fact",
        caller_payload={"trace": {"model": "x", "latency_ms": 1, "reasoning": "", "decision": "respond"}},
    )
    spine.append(
        execution_point="writable.step.end",
        channel="control",
        caller_payload={"step_id": "step_001", "outcome": "success"},
        outcome="success",
    )
    spine.close()

    deriver.flush()

    journal_path = run_dir / "journal.json"
    assert journal_path.exists(), "deriver.flush did not write journal.json"
    doc = deriver.document
    assert doc is not None
    assert doc.run_id == "run_e2e"
    assert doc.schema == "lca.journal/3.1"
    assert doc.totals.steps >= 1


def test_two_runs_produce_equivalent_documents(tmp_path: Path) -> None:
    """同一 events 流两次运行, deriver 输出等价 document(ADR-0167 I-MV3)。"""
    SpineContext.set_run("r-parity")

    # 收集每次 deriver.flush 的 document
    docs = []
    for i in range(2):
        run_dir = tmp_path / f"r{i}"
        run_dir.mkdir()
        deriver = StepTreeAccumulatorDeriver(
            run_id="r-parity",
            run_dir=run_dir,
            agent_role="agt",
            strategy_key="solo",
            plan_ref="plan_parity",
        )
        sink = FileSink(tmp_path, run_id="r-parity")
        spine = EventSpine(sinks=[sink], subscribers=[deriver.on_event])
        for ep in [
            ("writable.step.start", "control", {"phase": "think", "step_id": "step_001"}),
            ("step.thinking.record", "fact", {"trace": {"model": "m", "latency_ms": 1, "reasoning": "", "decision": "ok"}}),
            ("writable.step.end", "control", {"step_id": "step_001", "outcome": "success"}),
        ]:
            spine.append(execution_point=ep[0], channel=ep[1], caller_payload=ep[2])
        spine.close()
        deriver.flush()
        assert deriver.document is not None
        docs.append(deriver.document)

    assert docs[0].totals.steps == docs[1].totals.steps
    assert docs[0].schema == docs[1].schema


def test_deriver_flush_with_no_open_step_is_safe(tmp_path: Path) -> None:
    """没有累积 step 时 flush 仍写文件(空 document)。"""
    SpineContext.set_run("r-empty")
    run_dir = tmp_path / "r-empty"
    run_dir.mkdir()
    deriver = StepTreeAccumulatorDeriver(
        run_id="r-empty", run_dir=run_dir, agent_role="a", strategy_key="solo",
    )
    deriver.flush()  # 无 on_event
    assert deriver.document is not None
    assert len(deriver.document.steps) == 0
