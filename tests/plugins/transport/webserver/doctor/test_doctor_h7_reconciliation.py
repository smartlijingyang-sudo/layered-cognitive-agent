"""ADR-0244 PR-1 Task 3: Doctor H7 精准集合对账测试。

废除脆弱的步骤数启发式 (total_steps == tool_total < spine_total)，
改为精准集合比对与多工具感知：
1. 当 Run 中存在纯文本回复步骤且存在并发工具调用时，plural JournalStep 记录全部 tool_calls，H7 判定 ok=True；
2. 当面对 legacy 单数 step 且 spine 存在并发工具调用（同 step 多次 call）时，能正确识别 forked_tool_calls (ok=None) 而非假阳性报警；
3. 当存在真实丢失工具调用时，精确输出缺失的 invocation_id，判定 ok=False。
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.models.observability import (
    JournalMetadata,
    JournalStep,
    ReflectTrace,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
    append_step,
    close_document,
    empty_document,
)
from lca.infrastructure.observability.journal.step.projector import JournalDocumentWriter
from lca.plugins.transport.webserver.doctor.doctor import diagnose_step_tree


def _write_doc(tmp_path: Path, doc) -> Path:
    writer = JournalDocumentWriter(tmp_path / "journal.json")
    writer.write(doc)
    return tmp_path / "journal.json"


def _write_spine(tmp_path: Path, run_id: str, events: list[dict]) -> Path:
    spine = tmp_path / f"{run_id}.spine.jsonl"
    with spine.open("w", encoding="utf-8") as f:
        for i, ev in enumerate(events):
            full = {
                "event_id": f"e{i}",
                "category": "spine." + ev["execution_point"],
                "execution_point": ev["execution_point"],
                "channel": "fact",
                "payload": ev.get("payload", {}),
                "ts": str(1.0 + i),
            }
            f.write(json.dumps(full, ensure_ascii=False) + "\n")
    return spine


def _text_step(step_index: int) -> JournalStep:
    """A pure text reply step without tool calls."""
    return JournalStep(
        step_id=f"step-{step_index}",
        step_index=step_index,
        phase="think",
        entered_at=float(step_index),
        outcome="ok",
        thinking=ThinkingTrace(model="test-model", latency_ms=15),
        reflect=ReflectTrace(summary="pure text reply"),
    )


def test_h7_passes_with_text_step_and_plural_concurrent_tools(tmp_path: Path) -> None:
    """Run 含纯文本步骤 (step 1) 与并发工具步骤 (step 2 包含 2 个并发工具)。

    新版 JournalStep 支持复数 tool_calls 与 tool_results。
    此时 total_steps=2, tool_total=2, spine_total=2。
    H7 应精确对账并通过 (ok=True)。
    旧代码如果不读 step.tool_calls，只会读到 1 个工具，从而误报 mismatch。
    """
    meta = JournalMetadata(agent_role="assistant", strategy_key="solo", plan_ref="p", objective="multi-tool test")
    doc = empty_document(run_id="run_concurrent", trace_id="t1", metadata=meta, started_at=0.0)

    # Step 1: 纯文本回复
    doc = append_step(doc, _text_step(1))

    # Step 2: 包含 2 个并发工具调用
    tc1 = ToolCallRecord(invocation_id="inv-cmd-1", name="runCommand", arguments={"command": "ls"})
    tc2 = ToolCallRecord(invocation_id="inv-code-2", name="executeCode", arguments={"code": "print(1)"})
    tr1 = ToolResult(invocation_id="inv-cmd-1", ok=True, latency_ms=50)
    tr2 = ToolResult(invocation_id="inv-code-2", ok=True, latency_ms=80)

    doc = append_step(
        doc,
        JournalStep(
            step_id="step-2",
            step_index=2,
            phase="act",
            entered_at=2.0,
            outcome="ok",
            tool_call=tc1,
            tool_result=tr1,
            tool_calls=(tc1, tc2),
            tool_results=(tr1, tr2),
            thinking=ThinkingTrace(model="test-model", latency_ms=20),
            reflect=ReflectTrace(summary="two tools executed"),
        ),
    )
    doc = close_document(doc, outcome="completed", closed_at=5.0)
    path = _write_doc(tmp_path, doc)

    # Spine 记录 2 次 phase.tool.call.end
    _write_spine(
        tmp_path,
        "run_concurrent",
        [
            {
                "execution_point": "phase.tool.call.end",
                "payload": {"tool_name": "runCommand", "invocation_id": "inv-cmd-1", "ok": True, "step": 2},
            },
            {
                "execution_point": "phase.tool.call.end",
                "payload": {"tool_name": "executeCode", "invocation_id": "inv-code-2", "ok": True, "step": 2},
            },
        ],
    )

    report = diagnose_step_tree(path)
    h7 = report.hops["H7"]
    assert h7.ok is True, f"Expected H7.ok=True, got {h7.ok}, detail={h7.detail}"
    assert (h7.extra or {}).get("journal_tool_total") == 2
    assert (h7.extra or {}).get("spine_phase_tool_call_end_total") == 2


def test_h7_identifies_forked_tools_with_interleaved_text_steps_legacy(tmp_path: Path) -> None:
    """Legacy 单数 step 样本：含纯文本回复，且 step 2 并发 2 个工具但 journal 只记录 1 个。

    旧代码 heuristic: scan.total_steps (2) == scan.tool_total (1) < spine_total (2)
    因为 2 != 1，旧代码误判 forked=False，报错 mismatch (ok=False)！
    新对账机制：通过 spine 中 step 2 包含多条 phase.tool.call.end 识别为并发工具，判定 ok=None (forked)。
    """
    meta = JournalMetadata(agent_role="assistant", strategy_key="solo", plan_ref="p", objective="legacy fork test")
    doc = empty_document(run_id="run_legacy_fork", trace_id="t2", metadata=meta, started_at=0.0)

    # Step 1: 纯文本回复
    doc = append_step(doc, _text_step(1))

    # Step 2: 仅记录单个 tool_call (legacy)
    tc1 = ToolCallRecord(invocation_id="inv-cmd-1", name="runCommand", arguments={"command": "ls"})
    tr1 = ToolResult(invocation_id="inv-cmd-1", ok=True, latency_ms=50)
    doc = append_step(
        doc,
        JournalStep(
            step_id="step-2",
            step_index=2,
            phase="act",
            entered_at=2.0,
            outcome="ok",
            tool_call=tc1,
            tool_result=tr1,
            thinking=ThinkingTrace(model="test-model", latency_ms=20),
            reflect=ReflectTrace(summary="only one tool recorded in legacy step"),
        ),
    )
    doc = close_document(doc, outcome="completed", closed_at=5.0)
    path = _write_doc(tmp_path, doc)

    # Spine 记录 2 次 phase.tool.call.end (step 2 并发)
    _write_spine(
        tmp_path,
        "run_legacy_fork",
        [
            {
                "execution_point": "phase.tool.call.end",
                "payload": {"tool_name": "runCommand", "invocation_id": "inv-cmd-1", "ok": True, "step": 2},
            },
            {
                "execution_point": "phase.tool.call.end",
                "payload": {"tool_name": "executeCode", "invocation_id": "inv-code-2", "ok": True, "step": 2},
            },
        ],
    )

    report = diagnose_step_tree(path)
    h7 = report.hops["H7"]
    assert h7.ok is None, f"Expected H7.ok=None (forked), got {h7.ok}, detail={h7.detail}"
    assert (h7.extra or {}).get("forked_tool_calls") is True
    assert "并发工具调用" in h7.detail


def test_h7_detects_genuine_lost_tool_call_with_precise_difference(tmp_path: Path) -> None:
    """真实丢失工具调用：Spine 中有独立的步骤调用，但 Journal 完全丢失。

    Spine: step 1 (inv-1), step 2 (inv-2), step 3 (inv-3)
    Journal: 仅有 step 1 (inv-1), step 2 (inv-2)
    H7 判定 ok=False，并在 extra 和 detail 中准确指出 missing_in_journal 包含了 inv-3。
    """
    meta = JournalMetadata(agent_role="assistant", strategy_key="solo", plan_ref="p", objective="lost tool test")
    doc = empty_document(run_id="run_lost", trace_id="t3", metadata=meta, started_at=0.0)

    for i in (1, 2):
        tc = ToolCallRecord(invocation_id=f"inv-{i}", name="runCommand", arguments={"command": f"cmd {i}"})
        tr = ToolResult(invocation_id=f"inv-{i}", ok=True, latency_ms=50)
        doc = append_step(
            doc,
            JournalStep(
                step_id=f"step-{i}",
                step_index=i,
                phase="act",
                entered_at=float(i),
                outcome="ok",
                tool_call=tc,
                tool_result=tr,
                thinking=ThinkingTrace(model="test-model", latency_ms=10),
                reflect=ReflectTrace(summary=f"step {i}"),
            ),
        )
    doc = close_document(doc, outcome="completed", closed_at=5.0)
    path = _write_doc(tmp_path, doc)

    # Spine 有 3 个独立 step 的工具调用
    _write_spine(
        tmp_path,
        "run_lost",
        [
            {
                "execution_point": "phase.tool.call.end",
                "payload": {"tool_name": "runCommand", "invocation_id": f"inv-{i}", "ok": True, "step": i},
            }
            for i in (1, 2, 3)
        ],
    )

    report = diagnose_step_tree(path)
    h7 = report.hops["H7"]
    assert h7.ok is False
    assert (h7.extra or {}).get("forked_tool_calls") is False
    assert "missing_in_journal" in (h7.extra or {})
    assert "inv-3" in (h7.extra or {}).get("missing_in_journal", [])
