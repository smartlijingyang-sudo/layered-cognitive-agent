from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.models.observability.activity import (
    ActivityCategory,
    ActivityIntentNamer,
    ActivityItem,
    ActivityStatus,
)


def test_activity_item_schema_and_immutability():
    item = ActivityItem(
        id="call_001",
        run_id="run_100",
        assistant_id="asst_arch",
        category=ActivityCategory.TOOL,
        title="正在搜索 Gmail 邮件",
        summary="检索未读重要邮件",
        status=ActivityStatus.RUNNING,
        start_time="2026-10-02T14:00:00Z",
        icon="mail",
        params={"query": "is:unread"},
    )
    assert item.status == ActivityStatus.RUNNING
    assert item.title == "正在搜索 Gmail 邮件"
    assert item.params == {"query": "is:unread"}

    # extra="forbid" guard
    with pytest.raises(ValidationError):
        ActivityItem(
            id="call_002",
            run_id="run_100",
            assistant_id="asst_arch",
            category=ActivityCategory.TOOL,
            title="t",
            summary="s",
            status=ActivityStatus.RUNNING,
            start_time="2026-10-02T14:00:00Z",
            icon="mail",
            params={},
            forbidden_field="fail",
        )


def test_activity_intent_namer_rules():
    # Gmail search
    t1, s1, i1 = ActivityIntentNamer.name(
        "hatch_gws_cli", {"action": "search", "query": "meeting", "service": "gmail"}
    )
    assert t1 == "正在搜索 Gmail 邮件"
    assert "meeting" in s1
    assert i1 == "mail"

    # Gmail send
    t_send, s_send, i_send = ActivityIntentNamer.name(
        "GMAIL_SEND_EMAIL", {"to": "alice@example.com", "subject": "Quarterly Report"}
    )
    assert "alice@example.com" in t_send
    assert "Quarterly Report" in s_send
    assert i_send == "mail"

    # Google Drive
    t_drive, s_drive, i_drive = ActivityIntentNamer.name(
        "hatch_gws_cli", {"service": "drive", "query": "Q3-Plan"}
    )
    assert t_drive == "正在访问 Google Drive 文档"
    assert "Q3-Plan" in s_drive
    assert i_drive == "document"

    # GitHub
    t_gh, s_gh, i_gh = ActivityIntentNamer.name("github_list_prs", {"repo": "lca/core"})
    assert t_gh == "正在检索 GitHub 仓库"
    assert "lca/core" in s_gh
    assert i_gh == "github"

    # Shell / command dynamic deconstruction (INV-01)
    t2, s2, i2 = ActivityIntentNamer.name("run_shell", {"command": "git status -s"})
    assert "Running command" not in t2
    assert "Git" in t2 or "git" in t2 or "状态" in t2
    assert "git status" in s2
    assert i2 == "terminal"

    # Browser
    t3, s3, i3 = ActivityIntentNamer.name(
        "browser.spawn_task", {"url": "https://github.com/pulls", "task": "Check PRs"}
    )
    assert "github.com" in t3
    assert "Check PRs" in s3
    assert i3 == "browser"

    # Subagent
    t_sub, s_sub, i_sub = ActivityIntentNamer.name(
        "subagent.spawn", {"role": "代码审查员", "prompt": "审核PR差异"}
    )
    assert "代码审查员" in t_sub
    assert "审核PR差异" in s_sub
    assert i_sub == "robot"

    # Cron
    t_cron, _s_cron, i_cron = ActivityIntentNamer.name("cron.run", {"title": "每日数据备份"})
    assert "每日数据备份" in t_cron
    assert i_cron == "clock"

    # Fallback with description
    t4, _s4, i4 = ActivityIntentNamer.name(
        "custom_tool", {"description": "同步云端配置", "key": "val"}
    )
    assert t4 == "同步云端配置"
    assert i4 == "tool"


def test_activity_intent_namer_dynamic_deconstruction_no_running_command():
    test_cases = [
        (
            "run_shell",
            {"command": "sed -n '285,340p' runner.py"},
            "读取 runner.py (285-340行)",
        ),
        (
            "box_run_command",
            {"command": "grep -E 'seed_from_|rehydrate_' lca/"},
            "检索 seed_from_|rehydrate_ 关键词",
        ),
        (
            "shell",
            {"command": "git worktree add -b iter-restart-1640"},
            "创建工作树 iter-restart-1640",
        ),
        ("run_shell", {"command": "python tmp/test_restart.py"}, "执行 tmp/test_restart.py 验证"),
        ("writeFile", {"name": "tmp/add_seed.py"}, "创建脚本 tmp/add_seed.py"),
    ]
    for tool_name, args, expected_keyword in test_cases:
        title, _summary, _icon = ActivityIntentNamer.name(tool_name, args)
        assert "Running command" not in title, (
            f"Tool {tool_name} returned hardcoded 'Running command'"
        )
        assert any(k in title for k in expected_keyword.split()), (
            f"Expected keyword from '{expected_keyword}' in '{title}'"
        )


def test_activity_intent_namer_memory_tool_discovery_and_github_queries() -> None:
    t_mem, s_mem, i_mem = ActivityIntentNamer.name("memory_recall", {})
    assert t_mem == "检索认知长期记忆"
    assert s_mem == "联想相关知识与偏好"
    assert i_mem == "memory"

    t_find, s_find, i_find = ActivityIntentNamer.name("tool_search", {"query": "Google Drive"})
    assert t_find == "发现与检索工具"
    assert s_find == "检索: Google Drive"
    assert i_find == "tool"

    t_branch, s_branch, i_branch = ActivityIntentNamer.name(
        "GITHUB_LIST_BRANCHES",
        {"owner": "agents-builders", "repo": "layered-cognitive-agent"},
    )
    assert t_branch == "检索 GitHub 分支"
    assert s_branch == "agents-builders/layered-cognitive-agent"
    assert i_branch == "github"

    t_commit, s_commit, i_commit = ActivityIntentNamer.name(
        "GITHUB_LIST_COMMITS", {"owner": "test", "repo": "test-repo"}
    )
    assert t_commit == "查询 GitHub 提交记录"
    assert s_commit == "test/test-repo"
    assert i_commit == "github"


def test_activity_intent_namer_defaults_when_arguments_are_thin() -> None:
    assert ActivityIntentNamer.name("run_shell", {"command": "echo hi"}) == (
        "执行 echo 指令",
        "echo hi",
        "terminal",
    )
    assert ActivityIntentNamer.name("browser_navigate", {"url": "https://a.com/b"}) == (
        "Browsing a.com",
        "自动化网页浏览",
        "browser",
    )
    assert ActivityIntentNamer.name("subagent.spawn", {"role": "Tester"}) == (
        "执行子任务: Tester",
        "后台协同任务",
        "robot",
    )
    assert ActivityIntentNamer.name("unknown_tool_xyz", {}) == (
        "执行操作: unknown_tool_xyz",
        "处理中",
        "tool",
    )


def test_evidence_parser_five_elements_structure():
    from lca.contracts.models.observability.activity import StepEvidence, parse_step_evidence

    parsed = parse_step_evidence(
        tool_name="box_run_command",
        arguments={"command": 'ssh252 \'echo "ZZSTART"; sed -n "285,340p" runner.py\''},
        tool_result={
            "ok": True,
            "latency_ms": 3841,
            "stdout_head": "class ActivityProjector:\n    def __init__...",
        },
        thinking={"reasoning": "读取 runner 初始化逻辑并验证冷启动分支"},
    )
    assert isinstance(parsed, StepEvidence)
    assert "ssh252" in parsed.command
    assert parsed.duration_ms == 3841
    assert parsed.exit_code == 0
    assert len(parsed.code_snippets) > 0 or len(parsed.search_results) > 0
    assert parsed.conclusion is not None
    assert "验证" in parsed.conclusion or "完成" in parsed.conclusion or "成功" in parsed.conclusion
