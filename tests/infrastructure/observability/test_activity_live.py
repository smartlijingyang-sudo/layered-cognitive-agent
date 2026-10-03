"""New behavior tests: tool_name/current_step, execute.start refresh, catalog events, honest timestamps."""
from lca.contracts.models.observability.activity import ActivityIntentNamer, ActivityStatus
from lca.infrastructure.observability.activity_projector import ActivityProjector


def _p():
    return ActivityProjector()


def test_start_stores_tool_name_and_live_step():
    p = _p()
    item = p.feed_event({
        "execution_point": "phase.tool.call.start",
        "payload": {
            "invocation_id": "c1", "run_id": "r1", "assistant_id": "a1",
            "tool_name": "run_shell", "arguments": {"command": "ls -la"},
            "timestamp": "2026-10-03T08:00:00Z",
        },
    })
    assert item is not None
    assert item.tool_name == "run_shell"
    assert item.current_step == "正在执行命令：ls -la"
    assert item.status == ActivityStatus.RUNNING


def test_execute_start_refreshes_start_time_and_keeps_live():
    p = _p()
    p.feed_event({
        "execution_point": "phase.tool.call.start",
        "payload": {"invocation_id": "c1", "assistant_id": "a1",
                    "tool_name": "run_shell", "arguments": {"command": "sleep 60"},
                    "timestamp": "2026-10-03T08:00:00Z"},
    })
    updated = p.feed_event({
        "execution_point": "body.tool.execute.start",
        "payload": {"invocation_id": "c1", "assistant_id": "a1",
                    "timestamp": "2026-10-03T08:00:05Z"},
    })
    assert updated is not None
    assert updated.start_time == "2026-10-03T08:00:05Z"
    assert updated.current_step == "正在执行命令：sleep 60"
    assert updated.status == ActivityStatus.RUNNING


def test_execute_start_synthesizes_item_when_start_missed():
    p = _p()
    item = p.feed_event({
        "execution_point": "body.tool.execute.start",
        "payload": {"invocation_id": "c9", "assistant_id": "a1",
                    "tool_name": "browser_navigate", "arguments": {"url": "https://example.com/x"},
                    "timestamp": "2026-10-03T08:01:00Z"},
    })
    assert item is not None
    assert item.status == ActivityStatus.RUNNING
    assert item.tool_name == "browser_navigate"
    assert item.current_step == "正在浏览 example.com"


def test_end_clears_current_step():
    p = _p()
    p.feed_event({
        "execution_point": "phase.tool.call.start",
        "payload": {"invocation_id": "c1", "assistant_id": "a1",
                    "tool_name": "run_shell", "arguments": {"command": "ls"},
                    "timestamp": "2026-10-03T08:00:00Z"},
    })
    done = p.feed_event({
        "execution_point": "body.tool.execute.end",
        "payload": {"invocation_id": "c1", "assistant_id": "a1", "ok": True,
                    "latency_ms": 120, "timestamp": "2026-10-03T08:00:07Z"},
    })
    assert done.status == ActivityStatus.COMPLETED
    assert done.current_step is None
    assert done.duration_ms == 120


def test_catalog_tool_started_reaches_drawer():
    # 网关 catalog 事件之前到不了抽屉（死线）——现在必须能建项
    p = _p()
    item = p.feed_event({
        "execution_point": "ToolStarted",
        "payload": {"call_id": "g1", "tool_name": "gmail_search",
                    "args": {"query": "from:boss"}},
    })
    assert item is not None
    assert item.tool_name == "gmail_search"
    assert item.status == ActivityStatus.RUNNING
    assert item.current_step == "正在处理 Gmail"
    assert item.start_time == ""  # 诚实：没有时间戳不编造


def test_catalog_tool_denied_is_failed_with_reason():
    p = _p()
    p.feed_event({
        "execution_point": "ToolStarted",
        "payload": {"call_id": "g2", "tool_name": "shell_exec", "args": {}},
    })
    denied = p.feed_event({
        "execution_point": "ToolDenied",
        "payload": {"call_id": "g2", "tool_name": "shell_exec", "reason": "policy blocked"},
    })
    assert denied.status == ActivityStatus.FAILED
    assert "policy blocked" in (denied.result_summary or "")
    assert denied.current_step is None


def test_catalog_tool_invoked_success():
    p = _p()
    p.feed_event({
        "execution_point": "ToolStarted",
        "payload": {"call_id": "g3", "tool_name": "memory_recall", "args": {}},
    })
    done = p.feed_event({
        "execution_point": "ToolInvoked",
        "payload": {"call_id": "g3", "tool_name": "memory_recall",
                    "result": {"state": {"summary": "找到 3 条记忆"}}},
    })
    assert done.status == ActivityStatus.COMPLETED
    assert done.result_summary == "找到 3 条记忆"


def test_failed_end_carries_error_message():
    p = _p()
    p.feed_event({
        "execution_point": "step.tool_call.record",
        "payload": {"invocation_id": "c5", "assistant_id": "a1",
                    "tool_name": "run_shell", "arguments": {},
                    "timestamp": "2026-10-03T08:02:00Z"},
    })
    failed = p.feed_event({
        "execution_point": "body.tool.execute.end",
        "payload": {"invocation_id": "c5", "assistant_id": "a1", "ok": False,
                    "error": "exit code 1: file not found"},
    })
    assert failed.status == ActivityStatus.FAILED
    assert "exit code 1" in (failed.result_summary or "")


def test_cancel_clears_live_step_without_fake_timestamp():
    p = _p()
    p.feed_event({
        "execution_point": "phase.tool.call.start",
        "payload": {"invocation_id": "c6", "assistant_id": "a1",
                    "tool_name": "run_shell", "arguments": {},
                    "timestamp": "2026-10-03T08:03:00Z"},
    })
    cancelled = p.cancel_activity("a1", "c6")
    assert cancelled is not None
    assert cancelled.status == ActivityStatus.CANCELLED
    assert cancelled.current_step is None
    assert cancelled.end_time != "cancelled"  # 不再写假时间戳


def test_live_step_per_category_language():
    assert ActivityIntentNamer.live_step("run_shell", {"command": "echo hi"}) == "正在执行命令：echo hi"
    assert ActivityIntentNamer.live_step("browser_navigate", {"url": "https://a.com/b"}) == "正在浏览 a.com"
    assert ActivityIntentNamer.live_step("subagent.spawn", {"role": "Tester"}) == "子任务执行中：Tester"
    assert ActivityIntentNamer.live_step("memory_recall", {}) == "正在检索/更新记忆库"
    assert ActivityIntentNamer.live_step("unknown_tool_xyz", {}) == "正在处理中"
    # 长命令截断
    long_cmd = "x" * 100
    assert ActivityIntentNamer.live_step("run_shell", {"command": long_cmd}).endswith("...")
