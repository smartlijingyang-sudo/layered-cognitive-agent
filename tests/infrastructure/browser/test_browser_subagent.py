"""Tests for BrowserSubagent and browser tools (ADR-0248 §5.3 / s06, s13).

Invariants tested:
- INV-05: 浏览器子代理严禁持有声带工具（send_message 必须被物理剔除，零对用户通道发声能力）。
- 浏览器子代理动作调度与单屏锁联动。
"""

import pytest

from lca.contracts.models.browser.models import (
    BrowserAction,
    BrowserActionType,
)
from lca.infrastructure.browser.subagent import BrowserSubagent
from lca.infrastructure.computer.desktop_lock import DesktopLockManager


def test_browser_subagent_has_no_vocal_tools():
    """INV-05: 浏览器子代理工具集物理剔除 send_message，绝对禁止对外发声。"""
    subagent = BrowserSubagent(agent_id="browser_worker_1")
    tool_names = [tool.name for tool in subagent.get_tools()]

    # 严禁暴露 send_message
    assert "send_message" not in tool_names
    # 包含浏览器核心原语工具
    assert "browser_navigate" in tool_names
    assert "browser_screenshot" in tool_names


@pytest.mark.asyncio
async def test_browser_subagent_action_execution_with_desktop_lock():
    lock_mgr = DesktopLockManager(default_ttl_s=60)
    subagent = BrowserSubagent(agent_id="sub_browser_agent", lock_manager=lock_mgr)

    action = BrowserAction(
        action_type=BrowserActionType.NAVIGATE,
        url="https://example.com",
    )
    result = await subagent.execute_action("sess_test_b", action)

    assert result.success is True
    assert result.action_type == BrowserActionType.NAVIGATE
    assert result.url == "https://example.com"
    # 操作完成后桌面锁应当被释放
    assert lock_mgr.is_locked() is False
