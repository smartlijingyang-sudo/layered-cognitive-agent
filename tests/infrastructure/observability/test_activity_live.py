"""Activity projector behavior tests: start/end folding, catalog events, honest timestamps."""

from lca.contracts.models.observability.activity import (
    ActivityCategory,
    ActivityIntentNamer,
    ActivityStatus,
)
from lca.infrastructure.observability.activity_projector import ActivityProjector


def _p():
    return ActivityProjector()


def test_start_creates_running_item_with_intent():
    p = _p()
    item = p.feed_event(
        {
            "execution_point": "phase.tool.call.start",
            "payload": {
                "invocation_id": "c1",
                "run_id": "r1",
                "assistant_id": "a1",
                "tool_name": "run_shell",
                "arguments": {"command": "ls -la"},
                "timestamp": "2026-10-03T08:00:00Z",
            },
        }
    )
    assert item is not None
    assert item.status == ActivityStatus.RUNNING
    assert item.category == ActivityCategory.COMMAND
    assert item.title == "执行 ls 指令"
    assert item.summary == "ls -la"


def test_end_completes_item_with_duration():
    p = _p()
    p.feed_event(
        {
            "execution_point": "phase.tool.call.start",
            "payload": {
                "invocation_id": "c1",
                "assistant_id": "a1",
                "tool_name": "run_shell",
                "arguments": {"command": "ls"},
                "timestamp": "2026-10-03T08:00:00Z",
            },
        }
    )
    done = p.feed_event(
        {
            "execution_point": "body.tool.execute.end",
            "payload": {
                "invocation_id": "c1",
                "assistant_id": "a1",
                "ok": True,
                "latency_ms": 120,
                "timestamp": "2026-10-03T08:00:07Z",
            },
        }
    )
    assert done.status == ActivityStatus.COMPLETED
    assert done.duration_ms == 120
    assert done.end_time == "2026-10-03T08:00:07Z"


def test_catalog_tool_started_reaches_drawer():
    # 网关 catalog 事件之前到不了抽屉（死线）——现在必须能建项
    p = _p()
    item = p.feed_event(
        {
            "type": "ToolStarted",
            "payload": {
                "call_id": "g1",
                "tool_name": "gmail_search",
                "args": {"query": "from:boss"},
            },
        }
    )
    assert item is not None
    assert item.status == ActivityStatus.RUNNING
    assert item.category == ActivityCategory.TOOL
    assert item.start_time == ""  # 诚实：没有时间戳不编造


def test_catalog_tool_denied_is_failed_with_reason():
    p = _p()
    p.feed_event(
        {
            "type": "ToolStarted",
            "payload": {"call_id": "g2", "tool_name": "shell_exec", "args": {}},
        }
    )
    denied = p.feed_event(
        {
            "type": "ToolDenied",
            "payload": {"call_id": "g2", "tool_name": "shell_exec", "reason": "policy blocked"},
        }
    )
    assert denied.status == ActivityStatus.FAILED
    assert "policy blocked" in (denied.result_summary or "")


def test_catalog_tool_invoked_success():
    p = _p()
    p.feed_event(
        {
            "type": "ToolStarted",
            "payload": {"call_id": "g3", "tool_name": "memory_recall", "args": {}},
        }
    )
    done = p.feed_event(
        {
            "type": "ToolInvoked",
            "payload": {
                "call_id": "g3",
                "tool_name": "memory_recall",
                "result": {"state": {"summary": "找到 3 条记忆"}},
            },
        }
    )
    assert done.status == ActivityStatus.COMPLETED
    assert done.result_summary == "找到 3 条记忆"


def test_failed_end_carries_error_message():
    p = _p()
    p.feed_event(
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "invocation_id": "c5",
                "assistant_id": "a1",
                "tool_name": "run_shell",
                "arguments": {},
                "timestamp": "2026-10-03T08:02:00Z",
            },
        }
    )
    failed = p.feed_event(
        {
            "execution_point": "body.tool.execute.end",
            "payload": {
                "invocation_id": "c5",
                "assistant_id": "a1",
                "ok": False,
                "error": "exit code 1: file not found",
            },
        }
    )
    assert failed.status == ActivityStatus.FAILED
    assert "exit code 1" in (failed.result_summary or "")


def test_cancel_clears_without_fake_timestamp():
    p = _p()
    p.feed_event(
        {
            "execution_point": "phase.tool.call.start",
            "payload": {
                "invocation_id": "c6",
                "assistant_id": "a1",
                "tool_name": "run_shell",
                "arguments": {},
                "timestamp": "2026-10-03T08:03:00Z",
            },
        }
    )
    cancelled = p.cancel_activity("a1", "c6")
    assert cancelled is not None
    assert cancelled.status == ActivityStatus.CANCELLED
    assert cancelled.end_time is None  # 不再写 "cancelled" 假时间戳


def test_intent_namer_returns_title_summary_icon():
    assert ActivityIntentNamer.name("run_shell", {"command": "echo hi"}) == (
        "执行 echo 指令",
        "echo hi",
        "terminal",
    )
    assert (
        ActivityIntentNamer.name("browser_navigate", {"url": "https://a.com/b"})[0]
        == "Browsing a.com"
    )
    assert ActivityIntentNamer.name("subagent.spawn", {"role": "Tester"})[0] == "执行子任务: Tester"
    assert ActivityIntentNamer.name("memory_recall", {})[0] == "检索认知长期记忆"
    title, summary, _icon = ActivityIntentNamer.name("unknown_tool_xyz", {})
    assert title == "执行操作: unknown_tool_xyz"
    assert summary == "处理中"


def test_seed_from_traces_rehydrates_after_restart(tmp_path):
    """Kernel restart wipes memory; seed_from_traces pulls real activities back."""
    run_dir = tmp_path / "run_abc123"
    run_dir.mkdir()
    (run_dir / "journal.json").write_text(
        '{"run_id": "run_abc123", "steps": ['
        '{"entered_at": 1791003119.0, "exited_at": 1791003134.0,'
        ' "tool_calls": [{"invocation_id": "i1", "name": "run_shell",'
        ' "arguments": {"command": "echo hi"}}],'
        ' "tool_results": [{"invocation_id": "i1", "ok": true, "latency_ms": 42}]},'
        '{"entered_at": 1791003200.0, "exited_at": 1791003210.0,'
        ' "tool_calls": [{"invocation_id": "i2", "name": "browser_navigate",'
        ' "arguments": {"url": "https://x.com"}}],'
        ' "tool_results": [{"invocation_id": "i2", "ok": false, "error": "timeout"}]}'
        "]}",
        encoding="utf-8",
    )
    p = ActivityProjector()
    n = p.seed_from_traces(root_dir=tmp_path)
    assert n == 2
    acts = p.get_activities("default")
    assert len(acts) == 2
    by_id = {a.id: a for a in acts}
    ok_item = by_id["i1"]
    assert ok_item.status == ActivityStatus.COMPLETED
    assert ok_item.duration_ms == 42
    fail_item = by_id["i2"]
    assert fail_item.status == ActivityStatus.FAILED
    assert "timeout" in (fail_item.result_summary or "")


def test_seed_from_traces_missing_dir_is_graceful(tmp_path):
    p = ActivityProjector()
    assert p.seed_from_traces(root_dir=tmp_path / "nope") == 0
    assert p.get_activities("x") == []
