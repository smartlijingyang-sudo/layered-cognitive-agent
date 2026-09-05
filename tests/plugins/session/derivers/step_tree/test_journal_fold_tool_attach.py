"""fold_step_tree 工具事件 attach 回归(缺口 H-xref;run_a7ead118420b)。

真值层有 ``spine.body.tool.execute.start`` + ``step.tool_call.record`` /
``step.tool_result.record``,journal 却全空 —— 工具事件在
``brain.think.end`` 关帧之后才到达,旧 ``_resolve_target`` 只认
``open_step`` 与 ``payload.step_index`` 精确匹配,落空即 drop。

本文件锁定修复后的归属规则:精确匹配 → 时间窗兜底(最近已关帧)→
无帧才 drop。事件形态取自 run_a7ead118420b 的 spine.jsonl。
"""

from __future__ import annotations

from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree


def test_tool_records_attach_to_closed_header_step_exact_match() -> None:
    """step.*.record 在 brain.think.end 之后到达,step_index 命中已关帧。"""
    events = [
        {"execution_point": "brain.think.start", "payload": {}, "when": 1.0},
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001", "reason": "initial"},
            "when": 2.0,
        },
        {
            "execution_point": "brain.think.end",
            "payload": {},
            "outcome": "success",
            "when": 3.0,
        },
        {"execution_point": "phase.act.fold", "payload": {"phase": "act"}, "when": 3.5},
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "bash",
                "invocation_id": "toolu_01",
                "arguments": {"command": "echo proj"},
                "arguments_summary": "echo proj",
                "step_index": 1,
            },
            "phase": "act",
            "when": 4.0,
        },
        {
            "execution_point": "step.tool_result.record",
            "payload": {
                "tool_name": "bash",
                "invocation_id": "toolu_01",
                "ok": True,
                "stdout_head": "proj",
                "stdout_chars_total": 5,
                "step_index": 1,
            },
            "phase": "act",
            "when": 4.5,
        },
    ]
    doc = fold_step_tree(events, run_id="r_tool_exact", outcome="completed")
    assert doc.totals.steps == 1
    step = doc.steps[0]
    assert step.step_id == "step-001"
    assert step.tool_call is not None
    assert step.tool_call.name == "bash"
    assert step.tool_call.invocation_id == "toolu_01"
    assert step.tool_call.arguments == {"command": "echo proj"}
    assert step.tool_result is not None
    assert step.tool_result.ok is True
    assert step.tool_result.stdout_head == "proj"


def test_tool_records_attach_via_time_window_when_index_drifts() -> None:
    """无 header 的 planner 步多占帧号 → step_index 精确匹配落空 → 时间窗兜底。

    run_a7ead118420b 形态:第 1 个 brain.think 步无 LLM 请求,header 开的
    帧是 fold 索引 2,而 cursor 的 step_index 是 1(首个发布的 header)。
    工具事件必须归属刚关闭的 LLM 步,而不是被 drop。
    """
    events = [
        # planner 步:无 header,占帧 1
        {"execution_point": "brain.think.start", "payload": {}, "when": 1.0},
        {
            "execution_point": "brain.think.end",
            "payload": {},
            "outcome": "success",
            "when": 1.5,
        },
        # LLM 步:fold 帧 2,cursor step_index = 1
        {"execution_point": "brain.think.start", "payload": {}, "when": 2.0},
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001", "reason": "initial"},
            "when": 2.1,
        },
        {
            "execution_point": "brain.think.end",
            "payload": {},
            "outcome": "success",
            "when": 3.0,
        },
        {"execution_point": "phase.act.fold", "payload": {"phase": "act"}, "when": 3.2},
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "bash",
                "invocation_id": "toolu_02",
                "arguments": {"command": "echo x"},
                "step_index": 1,
            },
            "phase": "act",
            "when": 3.5,
        },
        {
            "execution_point": "step.tool_result.record",
            "payload": {
                "tool_name": "bash",
                "invocation_id": "toolu_02",
                "ok": True,
                "stdout_head": "x",
                "step_index": 1,
            },
            "phase": "act",
            "when": 3.6,
        },
    ]
    doc = fold_step_tree(events, run_id="r_tool_drift", outcome="completed")
    assert doc.totals.steps == 2
    planner, llm_step = doc.steps
    assert planner.tool_call is None
    assert planner.tool_result is None
    assert llm_step.step_id == "step-001"
    assert llm_step.tool_call is not None
    assert llm_step.tool_call.invocation_id == "toolu_02"
    assert llm_step.tool_result is not None
    assert llm_step.tool_result.stdout_head == "x"


def test_body_tool_execute_events_without_step_index_attach_to_last_closed() -> None:
    """``body.tool.execute.*`` 不携带 step_index,经时间窗兜底归属最近已关帧。"""
    events = [
        {"execution_point": "brain.think.start", "payload": {}, "when": 1.0},
        {
            "execution_point": "llm.request.header",
            "payload": {"step_id": "step-001", "reason": "initial"},
            "when": 2.0,
        },
        {
            "execution_point": "brain.think.end",
            "payload": {},
            "outcome": "success",
            "when": 3.0,
        },
        {
            "execution_point": "body.tool.execute.start",
            "payload": {"tool_name": "bash", "invocation_id": "dec_aa"},
            "when": 3.4,
        },
        {
            "execution_point": "body.tool.execute.end",
            "payload": {
                "ok": True,
                "latency_ms": 12,
                "stdout_head": "proj-fix",
                "stdout_chars_total": 9,
            },
            "outcome": "success",
            "when": 3.8,
        },
    ]
    doc = fold_step_tree(events, run_id="r_body_tool", outcome="completed")
    assert doc.totals.steps == 1
    step = doc.steps[0]
    assert step.tool_call is not None
    assert step.tool_call.name == "bash"
    assert step.tool_result is not None
    assert step.tool_result.stdout_head == "proj-fix"
    assert step.tool_result.latency_ms == 12


def test_tool_record_before_any_step_is_dropped() -> None:
    """早于首个 step 的工具事件无帧可挂 → drop,不抛、不建帧。"""
    events = [
        {
            "execution_point": "step.tool_call.record",
            "payload": {"tool_name": "bash", "step_index": 0},
            "phase": "act",
            "when": 1.0,
        },
    ]
    doc = fold_step_tree(events, run_id="r_orphan_tool")
    assert doc.totals.steps == 0


def test_body_tool_execute_end_ok_false_from_outcome() -> None:
    """body.tool.execute.end 缺 ok 字段时从 outcome 推导,不能 ``ok or True`` 恒真。"""
    events = [
        {"execution_point": "brain.think.start", "payload": {}, "when": 1.0},
        {"execution_point": "brain.think.end", "payload": {}, "outcome": "success", "when": 2.0},
        {
            "execution_point": "body.tool.execute.end",
            "payload": {"tool_name": "bash", "outcome": "failed", "ok": False},
            "when": 3.0,
        },
    ]
    doc = fold_step_tree(events, run_id="r_tool_fail", outcome="failed")
    step = doc.steps[0]
    assert step.tool_result is not None
    assert step.tool_result.ok is False


def test_exception_caught_marks_step_error_and_failed_outcome() -> None:
    """exception.caught 写入 step.error 且 metadata.outcome=failed。"""
    events = [
        {"execution_point": "brain.think.start", "payload": {}, "when": 1.0},
        {"execution_point": "brain.think.end", "payload": {}, "outcome": "success", "when": 2.0},
        {
            "execution_point": "body.tool.execute.end",
            "payload": {"tool_name": "search_skill", "outcome": "success"},
            "when": 3.0,
        },
        {
            "execution_point": "exception.caught",
            "payload": {
                "exception_class": "ValidationError",
                "exception_message": "category mapping missing",
            },
            "when": 4.0,
        },
    ]
    doc = fold_step_tree(events, run_id="r_exc", outcome="failed")
    assert doc.metadata.outcome == "failed"
    step = doc.steps[0]
    assert step.error == "category mapping missing"
    assert step.outcome == "failed"
    assert step.tool_result is not None
    assert step.tool_result.ok is True
