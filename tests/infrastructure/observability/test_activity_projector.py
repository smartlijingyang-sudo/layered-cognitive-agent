from __future__ import annotations

from lca.contracts.models.observability.activity import ActivityCategory, ActivityStatus
from lca.infrastructure.observability.activity_projector import ActivityProjector


def test_projector_folds_events_deterministically():
    projector = ActivityProjector()

    # 1. tool start event
    start_ev = {
        "execution_point": "phase.tool.call.start",
        "payload": {
            "invocation_id": "call_123",
            "run_id": "run_001",
            "assistant_id": "architect",
            "tool_name": "run_shell",
            "arguments": {"command": "ls -la"},
            "timestamp": "2026-10-02T10:00:00Z",
        },
    }
    item1 = projector.feed_event(start_ev)
    assert item1 is not None
    assert item1.status == ActivityStatus.RUNNING
    assert item1.title == "执行 ls 指令"
    assert "ls -la" in item1.summary
    assert item1.category == ActivityCategory.COMMAND

    # 2. tool end event
    end_ev = {
        "execution_point": "body.tool.execute.end",
        "payload": {
            "invocation_id": "call_123",
            "run_id": "run_001",
            "assistant_id": "architect",
            "tool_name": "run_shell",
            "ok": True,
            "latency_ms": 150,
            "message": {"content": "total 48\n-rw-r--r-- ..."},
            "timestamp": "2026-10-02T10:00:00.150Z",
        },
    }
    item2 = projector.feed_event(end_ev)
    assert item2 is not None
    assert item2.status == ActivityStatus.COMPLETED
    assert item2.duration_ms == 150
    assert "total 48" in (item2.result_summary or "")

    # 3. get snapshot items
    items = projector.get_activities(assistant_id="architect")
    assert len(items) == 1
    assert items[0].id == "call_123"
    assert items[0].status == ActivityStatus.COMPLETED


def test_projector_cancel_and_determinism():
    # INV-01: Pure projection, determinism upon replay
    events = [
        {
            "execution_point": "phase.tool.call.start",
            "payload": {
                "invocation_id": "call_sub",
                "run_id": "run_002",
                "assistant_id": "architect",
                "tool_name": "subagent.spawn",
                "arguments": {"role": "Tester", "prompt": "Run integration tests"},
                "timestamp": "2026-10-02T10:05:00Z",
            },
        },
    ]

    p1 = ActivityProjector()
    for ev in events:
        p1.feed_event(ev)

    p2 = ActivityProjector()
    for ev in events:
        p2.feed_event(ev)

    assert p1.get_activities("architect") == p2.get_activities("architect")

    # Cancel
    cancelled = p1.cancel_activity("architect", "call_sub")
    assert cancelled is not None
    assert cancelled.status == ActivityStatus.CANCELLED
    assert cancelled.result_summary == "User cancelled operation"


def test_get_activities_falls_back_to_unstamped_default_bucket():
    # Gateway tool events historically lack assistant_id; the projector
    # stores them under "default". get_activities must surface them so the
    # status drawer shows real runs even without per-assistant stamping.
    projector = ActivityProjector()
    start_ev = {
        "execution_point": "phase.tool.call.start",
        "payload": {
            "invocation_id": "call_default",
            "run_id": "run_003",
            "tool_name": "editFile",
            "arguments": {"path": "/home/u/a.md"},
            "timestamp": "2026-10-02T11:00:00Z",
        },
    }
    assert projector.feed_event(start_ev) is not None
    items = projector.get_activities(assistant_id="asst_any")
    assert len(items) == 1
    assert items[0].id == "call_default"
    assert items[0].assistant_id == "default"


def test_activity_projector_disk_cache_roundtrip(tmp_path):
    cache_file = tmp_path / "activity_cache.json"
    p1 = ActivityProjector(cache_path=cache_file, seed_traces=False)

    ev = {
        "execution_point": "phase.tool.call.start",
        "payload": {
            "invocation_id": "call_cached_1",
            "run_id": "run_cache",
            "assistant_id": "asst_cache",
            "tool_name": "tool_search",
            "arguments": {"query": "git"},
            "timestamp": "2026-10-03T12:00:00Z",
        },
    }
    p1.feed_event(ev)
    assert cache_file.is_file()

    # Re-instantiate projector and verify items are loaded from cache
    p2 = ActivityProjector(cache_path=cache_file, seed_traces=False)
    cached_items = p2.get_activities("asst_cache")
    assert len(cached_items) == 1
    assert cached_items[0].id == "call_cached_1"
    assert cached_items[0].title == "发现与检索工具"


def test_activity_projector_seed_from_traces(tmp_path):
    # Setup mock trace run directory
    run_dir = tmp_path / "run_test_abc"
    run_dir.mkdir(parents=True)
    journal_path = run_dir / "journal.json"

    import json

    mock_journal = {
        "run_id": "run_test_abc",
        "started_at": 1791000000.0,
        "steps": [
            {
                "step_index": 1,
                "entered_at": 1791000000.0,
                "exited_at": 1791000005.0,
                "duration_ms": 5000,
                "tool_calls": [
                    {
                        "name": "GITHUB_LIST_COMMITS",
                        "invocation_id": "toolu_abc_1",
                        "arguments": {"owner": "test", "repo": "test-repo"},
                    }
                ],
                "tool_results": [
                    {
                        "invocation_id": "toolu_abc_1",
                        "ok": True,
                        "latency_ms": 320,
                        "stdout_head": "commit history",
                        "delta_summary": "Found 10 commits",
                    }
                ],
            }
        ],
    }
    journal_path.write_text(json.dumps(mock_journal), encoding="utf-8")

    projector = ActivityProjector(cache_path=None, seed_traces=False)
    added = projector.seed_from_traces(root_dir=tmp_path)
    assert added == 1

    items = projector.get_activities("any_assistant")
    assert len(items) == 1
    assert items[0].id == "toolu_abc_1"
    assert items[0].title == "查询 GitHub 提交记录"
    assert items[0].status == ActivityStatus.COMPLETED
    assert items[0].duration_ms == 320
