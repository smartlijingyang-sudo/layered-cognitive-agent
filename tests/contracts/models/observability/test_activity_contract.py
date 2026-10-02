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
    t1, s1, i1 = ActivityIntentNamer.name("hatch_gws_cli", {"action": "search", "query": "meeting", "service": "gmail"})
    assert t1 == "正在搜索 Gmail 邮件"
    assert "meeting" in s1
    assert i1 == "mail"

    # Gmail send
    t_send, s_send, i_send = ActivityIntentNamer.name("GMAIL_SEND_EMAIL", {"to": "alice@example.com", "subject": "Quarterly Report"})
    assert "alice@example.com" in t_send
    assert "Quarterly Report" in s_send
    assert i_send == "mail"

    # Google Drive
    t_drive, s_drive, i_drive = ActivityIntentNamer.name("hatch_gws_cli", {"service": "drive", "query": "Q3-Plan"})
    assert t_drive == "正在访问 Google Drive 文档"
    assert "Q3-Plan" in s_drive
    assert i_drive == "document"

    # GitHub
    t_gh, s_gh, i_gh = ActivityIntentNamer.name("github_list_prs", {"repo": "lca/core"})
    assert t_gh == "正在检索 GitHub 仓库"
    assert "lca/core" in s_gh
    assert i_gh == "github"

    # Shell
    t2, s2, i2 = ActivityIntentNamer.name("run_shell", {"command": "git status -s"})
    assert t2 == "Running command"
    assert "git status" in s2
    assert i2 == "terminal"

    # Browser
    t3, s3, i3 = ActivityIntentNamer.name("browser.spawn_task", {"url": "https://github.com/pulls", "task": "Check PRs"})
    assert "github.com" in t3
    assert "Check PRs" in s3
    assert i3 == "browser"

    # Subagent
    t_sub, s_sub, i_sub = ActivityIntentNamer.name("subagent.spawn", {"role": "代码审查员", "prompt": "审核PR差异"})
    assert "代码审查员" in t_sub
    assert "审核PR差异" in s_sub
    assert i_sub == "robot"

    # Cron
    t_cron, _s_cron, i_cron = ActivityIntentNamer.name("cron.run", {"title": "每日数据备份"})
    assert "每日数据备份" in t_cron
    assert i_cron == "clock"

    # Fallback with description
    t4, _s4, i4 = ActivityIntentNamer.name("custom_tool", {"description": "同步云端配置", "key": "val"})
    assert t4 == "同步云端配置"
    assert i4 == "tool"
