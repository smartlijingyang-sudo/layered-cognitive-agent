"""ADR-0183 PR-9 — 单一 spine 写入入口 wiring 回归锁。

生产写入链(唯一):
``StdLoopCursor`` → ``SpineWritePortAdapter``(façade)→
``_spine_port.write_port_append`` → ``EventSpine.append``(façade)→
``_spine_port.spine_port_append``(唯一实现)→ FileSink →
``<run_dir>/<run_id>.spine.jsonl``。

本测试用真实 FileSink 钉死:
- cursor 的 advance / record_* / close 写入全部落盘;
- 落盘字段与文件布局不变(``<run_id>.spine.jsonl``,payload 携带
  incarnation / plan_ref);
- 写入实现唯一在 ``_spine_port``,EventSpine.append 与
  SpineWritePortAdapter.append 均为 façade 转发。
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor_payloads import (
    ThinkingRecord,
    ToolCallRecord,
    ToolResultRecord,
)
from lca.infrastructure.observability.loop_cursor.bind import SpineWritePortAdapter
from lca.infrastructure.observability.loop_cursor.std import StdLoopCursor
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink


def _build_cursor(tmp_path: Path, run_id: str) -> tuple[StdLoopCursor, EventSpine]:
    sink = FileSink(tmp_path, run_id=run_id)
    spine = EventSpine(sinks=[sink], run_id=run_id)
    cursor = StdLoopCursor(
        spine=SpineWritePortAdapter(spine),
        run_id=run_id,
        trace_id="t-wiring",
        incarnation=Incarnation(run_id=run_id, plan_ref="plan-wiring", incarnation_seq=1),
    )
    return cursor, spine


def _read_spine_events(tmp_path: Path, run_id: str) -> list[dict]:
    path = tmp_path / f"{run_id}.spine.jsonl"
    assert path.exists(), f"missing spine file: {path}"
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_cursor_step_writes_land_in_run_spine_file(tmp_path: Path) -> None:
    """cursor 一个完整 step 的写入全部落 ``<run_id>.spine.jsonl``。"""
    run_id = "run-wiring-step"
    cursor, spine = _build_cursor(tmp_path, run_id)
    try:
        cursor.advance(
            "perceive", objective_kind="system_role", objective="collect", summary="seen"
        )
        cursor.advance("think", objective_kind="user_text", objective="hi", summary="plan")
        cursor.record_thinking(
            ThinkingRecord(
                content_digest="sha256:0",
                content_path=None,
                token_count=30,
                thinking_kind="reasoning",
            )
        )
        cursor.advance("act", objective_kind="system_role", objective="run tool", summary="act")
        cursor.record_tool_call(
            ToolCallRecord(
                tool_name="echo",
                args_digest="sha256:1",
                args_payload_path=None,
                call_seq=1,
            )
        )
        cursor.record_tool_result(
            ToolResultRecord(
                tool_name="echo",
                result_digest="sha256:2",
                result_path=None,
                outcome="ok",
            )
        )
        cursor.close("completed")
    finally:
        spine.flush()
        spine.close()

    events = _read_spine_events(tmp_path, run_id)
    eps = [e["execution_point"] for e in events]
    assert "phase.perceive.fold" in eps
    assert "phase.think.fold" in eps
    assert "step.thinking.record" in eps
    assert "phase.act.fold" in eps
    assert "step.tool_call.record" in eps
    assert "step.tool_result.record" in eps
    assert "writable.iteration.closing" in eps

    for event in events:
        assert event["run_id"] == run_id
        # write_port_append 把 incarnation 注入 payload(ADR-0169 L14)
        assert event["payload"]["incarnation"] == 1


def test_cursor_fold_payload_carries_identity(tmp_path: Path) -> None:
    """phase fold EP 携带 plan_ref / step_index;phase 字段 = cursor 当前 phase。"""
    run_id = "run-wiring-fold"
    cursor, spine = _build_cursor(tmp_path, run_id)
    try:
        cursor.advance(
            "perceive", objective_kind="system_role", objective="collect", summary="seen"
        )
    finally:
        spine.flush()
        spine.close()

    events = _read_spine_events(tmp_path, run_id)
    fold = next(e for e in events if e["execution_point"] == "phase.perceive.fold")
    assert fold["payload"]["plan_ref"] == "plan-wiring"
    assert fold["payload"]["objective_kind"] == "system_role"
    assert fold["payload"]["step_index"] == 0
    assert fold["phase"] == "perceive"


def test_spine_write_impl_lives_only_in_spine_port() -> None:
    """写入实现唯一在 ``_spine_port``;event_spine / bind 均为 façade 转发。

    ADR-0183 PR-9 架构门禁的代码级回归锁(与
    ``rg "def append" event_spine.py bind.py`` 至多一个转发配套)。
    """
    repo_root = Path(__file__).resolve().parents[2]
    port_src = (
        repo_root / "lca/infrastructure/observability/loop_cursor/_spine_port.py"
    ).read_text(encoding="utf-8")
    spine_src = (repo_root / "lca/infrastructure/observability/spine/event_spine.py").read_text(
        encoding="utf-8"
    )
    bind_src = (repo_root / "lca/infrastructure/observability/loop_cursor/bind.py").read_text(
        encoding="utf-8"
    )

    # 唯一实现:sink 写入与 hash chain 只在 _spine_port
    assert "sink.write(record)" in port_src
    assert "sink.write(record)" not in spine_src
    # EventSpine.append façade → spine_port_append
    assert "spine_port_append" in spine_src
    # SpineWritePortAdapter.append façade → write_port_append
    assert "write_port_append" in bind_src
