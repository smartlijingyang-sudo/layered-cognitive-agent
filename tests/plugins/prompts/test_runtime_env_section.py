"""Tests for ADR-0255 Runtime row and Developer timestamp section rendering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.plugins.prompts.sections.runtime_env import (
    DeveloperTimestampSection,
    RuntimeEnvSection,
    render_developer_timestamp,
    render_runtime_row,
)


def test_render_runtime_row_default():
    row = render_runtime_row()
    assert row.startswith("Runtime: session=main chat | os=linux")
    assert "model=" in row
    assert "shell=bash" in row
    assert "depth=0" in row
    assert "max_depth=2" in row
    assert "can_spawn=yes" in row


def test_render_runtime_row_custom():
    row = render_runtime_row(  # noqa: S604
        session="side chat",
        os_name="linux",
        model="qwen3.7-plus",
        shell="zsh",
        chat="side",
        depth=1,
        max_depth=2,
        can_spawn=False,
    )
    assert (
        row
        == "Runtime: session=side chat | os=linux | model=qwen3.7-plus | shell=zsh | chat=side | depth=1 | max_depth=2 | can_spawn=no"
    )


def test_render_developer_timestamp_explicit():
    # CST is UTC+8
    cst = timezone(timedelta(hours=8), name="CST")
    dt = datetime(2026, 10, 1, 11, 34, 53, tzinfo=cst)
    ts = render_developer_timestamp(dt=dt, tz_name="Asia/Shanghai", sent_from="web")
    assert "[Thu 2026-10-01 11:34:53 CST] [client_timezone=Asia/Shanghai]" in ts
    assert "Sent from: web" in ts


def test_runtime_env_section_render():
    sec = RuntimeEnvSection()
    profile = RoleProfile(
        role="assistant",
        goal="help user",
        backstory="test",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    out = sec.render(role_profile=profile, tools=())
    assert out.text.startswith("Runtime: session=main chat")


def test_developer_timestamp_section_render():
    sec = DeveloperTimestampSection()
    profile = RoleProfile(
        role="assistant",
        goal="help user",
        backstory="test",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    out = sec.render(role_profile=profile, tools=())
    assert "[client_timezone=" in out.text
    assert "Sent from: " in out.text
