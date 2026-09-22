"""Tests for WechatMessageFormatter ensuring parity with LobeHub replyTemplate.ts."""

from lca.infrastructure.channels.wechat.formatter import (
    BRANCH_ICON,
    EMOJI_THINKING,
    TOOL_COMPLETED_ICON,
    TOOL_PENDING_ICON,
    WechatMessageFormatter,
)


def test_constants_match_lobehub_native():
    assert EMOJI_THINKING == "💭"
    assert TOOL_PENDING_ICON == "○"
    assert TOOL_COMPLETED_ICON == "⏺"
    assert BRANCH_ICON == "⎿"


def test_render_thinking_only():
    formatted = WechatMessageFormatter.format_step_progress(
        step_type="think",
        thinking_text="正在分析系统磁盘状态...",
    )
    assert formatted == "💭 正在分析系统磁盘状态..."


def test_render_pending_tools_calling():
    tools_calling = [
        {"identifier": "local", "api_name": "runCommand", "summary_arg": 'cmd: "df -h"'},
    ]
    formatted = WechatMessageFormatter.format_step_progress(
        step_type="think",
        tools_calling=tools_calling,
    )
    assert formatted == '○ **local·runCommand**(cmd: "df -h")'


def test_render_completed_tools_calling_with_summary_and_header():
    tools_calling = [
        {"identifier": "local", "api_name": "runCommand", "summary_arg": 'cmd: "df -h"'},
    ]
    tools_result = [
        {"output": "Filesystem Size Used Avail Use% Mounted on\n/dev/sda1 50G 20G 30G 40% /", "is_success": True},
    ]
    formatted = WechatMessageFormatter.format_step_progress(
        step_type="act",
        tools_calling=tools_calling,
        tools_result=tools_result,
        total_tool_calls=1,
        elapsed_seconds=1.5,
    )
    assert "> 共 **1** 次工具调用 · 1.5s" in formatted
    assert '⏺ **local·runCommand**(cmd: "df -h")\n⎿  success: 70 chars' in formatted


def test_render_tool_failure_summary():
    tools_calling = [
        {"identifier": "builtin", "api_name": "search", "summary_arg": 'q: "test"'},
    ]
    tools_result = [
        {"output": "Connection timeout", "is_success": False},
    ]
    formatted = WechatMessageFormatter.format_step_progress(
        step_type="act",
        tools_calling=tools_calling,
        tools_result=tools_result,
        total_tool_calls=2,
        elapsed_seconds=3.2,
    )
    assert "> 共 **2** 次工具调用 · 3.2s" in formatted
    assert '⏺ **builtin·search**(q: "test")' in formatted
    assert "⎿  error: 18 chars" in formatted
