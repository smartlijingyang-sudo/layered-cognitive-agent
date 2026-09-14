"""fold_step_tree 工具事件 attach 测试。

工具事件(step.tool_call.record / step.tool_result.record /
body.tool.execute.start / body.tool.execute.end)按时间窗挂到 open
step;无 open step 时挂到最近 closed step(兜底)。
"""

from __future__ import annotations

from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree


def _hdr(sid: str, when: int) -> dict[str, object]:
    return {"execution_point": "llm.request.header", "payload": {"step_id": sid}, "when": when}


def _phase(kind: str, when: int) -> dict[str, object]:
    return {"execution_point": f"phase.{kind}.fold", "payload": {}, "when": when}


def _tool_call(name: str, when: int, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"tool_name": name, "invocation_id": f"inv_{name}", **extra}
    return {"execution_point": "step.tool_call.record", "payload": payload, "when": when}


def _tool_result(ok: bool, when: int, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"ok": ok, "invocation_id": "inv_x", **extra}
    return {"execution_point": "step.tool_result.record", "payload": payload, "when": when}


def test_tool_records_attach_to_open_step() -> None:
    """step 打开期间 tool_call/result → 挂到当前 step。"""
    events = [
        _hdr("step-001", when=1),
        _tool_call(
            "executeCode",
            when=2,
            arguments={"code": "1+1"},
            arguments_summary="executeCode(python)",
        ),
        _tool_result(ok=True, when=3, delta_summary="ok", stdout_head="2"),
    ]
    doc = fold_step_tree(events, run_id="r_tool")
    assert len(doc.steps) == 1
    assert doc.steps[0].tool_call is not None
    assert doc.steps[0].tool_call.name == "executeCode"
    assert doc.steps[0].tool_result is not None
    assert doc.steps[0].tool_result.ok is True


def test_body_tool_execute_end_ok_false_from_outcome() -> None:
    """body.tool.execute.end payload.outcome='failed' → ok=False。"""
    events = [
        _hdr("step-001", when=1),
        {
            "execution_point": "body.tool.execute.end",
            "payload": {"outcome": "failed", "invocation_id": "inv_1", "delta_summary": "boom"},
            "when": 2,
        },
    ]
    doc = fold_step_tree(events, run_id="r_body_fail")
    assert doc.steps[0].tool_result is not None
    assert doc.steps[0].tool_result.ok is False


def test_body_tool_execute_does_not_clobber_step_tool_evidence() -> None:
    """body.tool.execute.* 与 step.tool_*.record 互不覆写(各自累积)。"""
    events = [
        _hdr("step-001", when=1),
        _tool_call("search", when=2, arguments={"q": "x"}, arguments_summary="search(x)"),
        {
            "execution_point": "body.tool.execute.start",
            "payload": {"tool_name": "search", "invocation_id": "inv_search"},
            "when": 3,
        },
        _tool_result(ok=True, when=4, delta_summary="hit"),
    ]
    doc = fold_step_tree(events, run_id="r_clobber")
    # step.tool_call 已被 step.tool_call.record 占据;body.tool.execute.start
    # 不再覆写(同 invocation_id),但 fold 引擎不重复填充。
    tc = doc.steps[0].tool_call
    assert tc is not None
    assert tc.name == "search"


def test_exception_caught_marks_step_error_and_failed_outcome() -> None:
    """exception.caught → 当前 step.error 非空 + step.outcome=failed。"""
    events = [
        _hdr("step-001", when=1),
        {
            "execution_point": "exception.caught",
            "payload": {"exception_message": "boom", "exception_class": "ValueError"},
            "when": 2,
        },
    ]
    doc = fold_step_tree(events, run_id="r_exc")
    assert doc.metadata.outcome == "failed"
    assert doc.steps[0].error is not None
    assert "boom" in doc.steps[0].error
