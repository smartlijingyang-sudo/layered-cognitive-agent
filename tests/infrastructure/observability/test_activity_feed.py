"""``ActivityFeed`` — run-level activity rows folded from run artifacts on read.

Pins the contract the Status screen reads: one row per run, terminated runs fold
their journal, live runs fold their spine, abandoned runs stay out, and the fold
never writes to the ledger it describes.
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.observability.activity import (
    ActivityCategory,
    ActivityStatus,
)
from lca.infrastructure.observability.activity_feed import (
    ActivityFeed,
    get_activity_feed,
)
from lca.infrastructure.persistence.run_paths import default_runs_root
from tests.support.run_artifacts import (
    OBJECTIVE,
    TRACE_ID,
    spine_line,
    tool_line,
    write_live_run,
    write_terminated_run,
)


def _tree_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            info = path.stat()
            snapshot[str(path.relative_to(root))] = (info.st_mtime_ns, info.st_size)
    return snapshot


def test_terminated_run_folds_its_journal_into_one_row(tmp_path: Path) -> None:
    write_terminated_run(
        tmp_path,
        "run_a1b2c3d4e5f6",
        steps=(
            (("tool_search", {"query": "Google Drive"}),),
            (
                ("run_shell", {"command": "git status -s"}),
                ("listFiles", {"path": "."}),
            ),
        ),
    )

    rows = ActivityFeed(tmp_path).list_activities()

    assert [row.id for row in rows] == ["run_a1b2c3d4e5f6"]
    row = rows[0]
    assert row.run_id == "run_a1b2c3d4e5f6"
    assert row.assistant_id == ""
    assert row.status is ActivityStatus.COMPLETED
    assert row.category is ActivityCategory.TOOL
    assert row.title == OBJECTIVE
    assert row.summary == "调用 3 个工具：tool_search、run_shell、listFiles"
    assert row.tool_name == "tool_search"
    assert row.icon == "tool"
    assert row.start_time == "2026-10-03T15:38:01+00:00"
    assert row.end_time == "2026-10-03T15:38:23+00:00"
    assert row.duration_ms == 22000
    assert row.current_step is None


def test_live_run_folds_its_spine_into_a_running_row(tmp_path: Path) -> None:
    write_live_run(
        tmp_path,
        "run_0f1e2d3c4b5a",
        tool_calls=[
            ("tool_search", {"query": "Google Drive"}),
            ("run_shell", {"command": "git status -s"}),
        ],
    )

    rows = ActivityFeed(tmp_path).list_activities(live_run_ids=("run_0f1e2d3c4b5a",))

    assert [row.id for row in rows] == ["run_0f1e2d3c4b5a"]
    row = rows[0]
    assert row.status is ActivityStatus.RUNNING
    assert row.current_step == "查看 Git 工作区状态"
    assert row.title == OBJECTIVE
    assert row.summary == "调用 2 个工具：tool_search、run_shell"
    assert row.start_time == "2026-10-03T15:42:29+00:00"
    assert row.end_time is None
    assert row.duration_ms is None


def test_unterminated_run_nobody_is_executing_stays_out_of_the_feed(tmp_path: Path) -> None:
    write_terminated_run(tmp_path, "run_a1b2c3d4e5f6")
    write_live_run(tmp_path, "run_abandoned0001")

    rows = ActivityFeed(tmp_path).list_activities()

    assert [row.id for row in rows] == ["run_a1b2c3d4e5f6"]


def test_start_time_is_recovered_from_the_spine_when_the_journal_has_none(tmp_path: Path) -> None:
    run_dir = write_terminated_run(
        tmp_path,
        "run_02419387128c",
        objective="ping",
        outcome="failed",
        started_at=0.0,
        closed_at=None,
    )
    spine = run_dir / "run_02419387128c.spine.jsonl"
    spine.write_text(
        spine_line(
            "run_02419387128c",
            1,
            "kernel.run.start",
            {"run_id": "run_02419387128c", "trace_id": TRACE_ID},
            "2026-10-03T15:17:31Z",
        )
        + "\n",
        encoding="utf-8",
    )

    rows = ActivityFeed(tmp_path).list_activities()

    assert [row.id for row in rows] == ["run_02419387128c"]
    assert rows[0].start_time == "2026-10-03T15:17:31+00:00"
    assert rows[0].status is ActivityStatus.FAILED
    assert rows[0].end_time is None
    assert rows[0].duration_ms is None


def test_rows_come_back_newest_first(tmp_path: Path) -> None:
    write_terminated_run(tmp_path, "run_oldest000001", started_at=1791041881.0)
    write_terminated_run(tmp_path, "run_middle000001", started_at=1791042000.0)
    write_terminated_run(tmp_path, "run_newest000001", started_at=1791042100.0)

    rows = ActivityFeed(tmp_path).list_activities()

    assert [row.id for row in rows] == [
        "run_newest000001",
        "run_middle000001",
        "run_oldest000001",
    ]
    assert [row.start_time for row in rows] == [
        "2026-10-03T15:41:40+00:00",
        "2026-10-03T15:40:00+00:00",
        "2026-10-03T15:38:01+00:00",
    ]


def test_limit_keeps_the_newest_start_times(tmp_path: Path) -> None:
    # 后创建的 run 目录 mtime 更新，但其 start_time 更旧。limit 必须按
    # start_time 排序后截断，而不是按目录 mtime 截断。
    write_terminated_run(tmp_path, "run_new_start", started_at=1791042100.0)
    write_terminated_run(tmp_path, "run_old_start", started_at=1791041881.0)

    rows = ActivityFeed(tmp_path, limit=1).list_activities()

    assert [row.id for row in rows] == ["run_new_start"]


def test_harness_run_dirs_never_reach_the_feed(tmp_path: Path) -> None:
    write_terminated_run(tmp_path, "run_a1b2c3d4e5f6")
    write_terminated_run(tmp_path, "run_test_abc123")
    write_terminated_run(tmp_path, "run_e2e_smoke_0001")

    rows = ActivityFeed(tmp_path).list_activities(
        live_run_ids=("run_test_abc123", "run_e2e_smoke_0001")
    )

    assert [row.id for row in rows] == ["run_a1b2c3d4e5f6"]


def test_injected_system_context_is_trimmed_off_the_objective(tmp_path: Path) -> None:
    write_terminated_run(
        tmp_path,
        "run_a1b2c3d4e5f6",
        objective=(
            "帮我看一下\n  这份   合同\n\n"
            "<!-- SYSTEM CONTEXT (NOT PART OF USER QUERY) -->\n"
            "<context.instruction>following part contains context information injected by the "
            "system.</context.instruction>\n"
            '<files_info>\n<files>\n<file id="att_1" name="contract.pdf" type="application/pdf" '
            'size="20480"></file>\n</files>\n</files_info>\n'
            "<!-- END SYSTEM CONTEXT -->"
        ),
    )

    rows = ActivityFeed(tmp_path).list_activities()

    assert [row.title for row in rows] == ["帮我看一下 这份 合同"]


def test_zero_tool_run_reports_a_direct_reply(tmp_path: Path) -> None:
    write_terminated_run(tmp_path, "run_a1b2c3d4e5f6", objective="你好")

    rows = ActivityFeed(tmp_path).list_activities()

    assert [row.id for row in rows] == ["run_a1b2c3d4e5f6"]
    assert rows[0].summary == "未调用工具，直接回复"
    assert rows[0].title == "你好"
    assert rows[0].tool_name == ""
    assert rows[0].icon == "chat"
    assert rows[0].category is ActivityCategory.TOOL


def test_listing_activities_writes_nothing_under_the_runs_root(tmp_path: Path) -> None:
    write_terminated_run(tmp_path, "run_a1b2c3d4e5f6")
    live_spine = write_live_run(
        tmp_path, "run_0f1e2d3c4b5a", tool_calls=[("tool_search", {"query": "Google Drive"})]
    )
    before = _tree_snapshot(tmp_path)

    rows = ActivityFeed(tmp_path).list_activities(live_run_ids=("run_0f1e2d3c4b5a",))

    assert len(rows) == 2
    assert _tree_snapshot(tmp_path) == before
    assert live_spine.read_text(encoding="utf-8").count("\n") == 3


def test_the_memo_is_a_read_cache_over_the_spine(tmp_path: Path) -> None:
    run_id = "run_0f1e2d3c4b5a"
    spine = write_live_run(
        tmp_path, run_id, tool_calls=[("tool_search", {"query": "Google Drive"})]
    )
    feed = ActivityFeed(tmp_path)

    first = feed.list_activities(live_run_ids=(run_id,))
    assert [row.summary for row in first] == ["调用 1 个工具：tool_search"]
    assert feed.list_activities(live_run_ids=(run_id,)) == first

    with spine.open("a", encoding="utf-8") as handle:
        handle.write(
            tool_line(
                run_id, 480, "run_shell", {"command": "git status -s"}, "2026-10-03T15:43:02Z"
            )
            + "\n"
        )

    grown = feed.list_activities(live_run_ids=(run_id,))
    assert [row.summary for row in grown] == ["调用 2 个工具：tool_search、run_shell"]
    assert [row.current_step for row in grown] == ["查看 Git 工作区状态"]

    feed.invalidate()
    assert feed.list_activities(live_run_ids=(run_id,)) == grown


def test_get_activity_feed_returns_one_feed_on_the_default_root() -> None:
    feed = get_activity_feed()

    assert feed is get_activity_feed()
    assert feed.runs_root == default_runs_root()
