"""Tests for BrowserSubagent and browser tools (ADR-0248 §5.3 / s06, s13).

Invariants tested:
- INV-05: 浏览器子代理严禁持有声带工具（send_message 必须被物理剔除，零对用户通道发声能力）。
- 浏览器子代理动作调度与单屏锁联动（RA-146：分发走注入的 executor，不再伪造结果）。
"""

import asyncio

import pytest

from lca.contracts.models.browser.models import (
    BrowserAction,
    BrowserActionResult,
    BrowserActionType,
)
from lca.infrastructure.browser.subagent import BrowserSubagent
from lca.infrastructure.computer.desktop_lock import DesktopLockCoordinator
from lca.infrastructure.tools.browser.tools import build_browser_tools


class _VocalTool:
    """冒充发声工具：验证注入的工具集仍被 INV-05 过滤。"""

    name = "send_message"


def test_browser_subagent_has_no_vocal_tools():
    """INV-05: 注入的工具集仍被物理剔除 send_message，绝对禁止对外发声。"""
    tools = [*build_browser_tools(), _VocalTool()]
    subagent = BrowserSubagent(agent_id="browser_worker_1", tools=tools)
    tool_names = [tool.name for tool in subagent.get_tools()]

    # 严禁暴露 send_message（即使调用方显式注入了也被剔除）
    assert "send_message" not in tool_names
    # 包含浏览器核心原语工具
    assert "browser_navigate" in tool_names
    assert "browser_screenshot" in tool_names


@pytest.mark.asyncio
async def test_browser_subagent_action_execution_with_desktop_lock():
    """RA-146：动作分发走注入的 executor；recording fake 钉住真实交互。"""
    lock_mgr = DesktopLockCoordinator(default_ttl_s=60)
    calls: list[BrowserAction] = []

    async def fake_executor(action: BrowserAction) -> BrowserActionResult:
        calls.append(action)
        return BrowserActionResult(
            action_type=action.action_type,
            success=True,
            url=action.url,
            title="Real Page Title",
        )

    subagent = BrowserSubagent(
        agent_id="sub_browser_agent",
        tools=build_browser_tools(),
        action_executor=fake_executor,
        lock_manager=lock_mgr,
    )

    action = BrowserAction(
        action_type=BrowserActionType.NAVIGATE,
        url="https://example.com",
    )
    result = await subagent.execute_action("sess_test_b", action)

    # executor 真被调用，且拿到的是原始 action（不是伪造分支的硬编码值）
    assert calls == [action]
    assert result.success is True
    assert result.action_type == BrowserActionType.NAVIGATE
    assert result.url == "https://example.com"
    # title 来自 executor，不是伪造的 "Navigated Page"
    assert result.title == "Real Page Title"
    # 操作完成后桌面锁应当被释放
    assert lock_mgr.is_locked() is False


@pytest.mark.asyncio
async def test_browser_subagent_action_execution_without_executor_fails_closed():
    """RA-146：未注入 executor 时 fail-closed——诚实返回失败，不伪造成功。"""
    subagent = BrowserSubagent(
        agent_id="no_executor_agent",
        tools=build_browser_tools(),
    )
    action = BrowserAction(
        action_type=BrowserActionType.NAVIGATE,
        url="https://example.com",
    )
    result = await subagent.execute_action("sess_no_exec", action)

    assert result.success is False
    assert result.action_type == BrowserActionType.NAVIGATE
    assert result.error is not None


def test_browser_subagent_accepts_sync_executor():
    """executor 同步/异步皆可：同步返回值直接透传。"""
    subagent = BrowserSubagent(
        agent_id="sync_executor_agent",
        tools=[],
        action_executor=lambda action: BrowserActionResult(
            action_type=action.action_type, success=True
        ),
    )
    result = asyncio.run(
        subagent.execute_action(
            "sess_sync", BrowserAction(action_type=BrowserActionType.CLOSE)
        )
    )
    assert result.success is True
    assert result.action_type == BrowserActionType.CLOSE
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action_type", [BrowserActionType.TYPE, BrowserActionType.EXTRACT_TEXT]
)
async def test_execute_via_driver_delegates_to_shared_executor(
    monkeypatch, action_type
):
    """RA-154: driver-only subagent 不再手写分发表，经共享执行 seam 分发。

    钉住三点：调用了 build_browser_action_executor；driver 与 session_id
    透传；原始 action 对象流向 executor。
    """
    from lca.infrastructure.browser import subagent as subagent_mod

    seen: dict = {}

    async def fake_execute(action):
        seen["action"] = action
        return BrowserActionResult(action_type=action.action_type, success=True)

    def fake_build(*args, **kwargs):
        seen["kwargs"] = kwargs
        return fake_execute

    monkeypatch.setattr(subagent_mod, "build_browser_action_executor", fake_build)

    driver = object()  # 仅验证透传，不触碰真实 driver
    subagent = BrowserSubagent(agent_id="drv_only", driver=driver)
    action = BrowserAction(action_type=action_type, selector="#name", text="hi")
    result = await subagent.execute_action("sess_x", action)

    assert result.success is True
    assert seen["kwargs"]["driver"] is driver
    assert seen["kwargs"]["session_id"] == "sess_x"
    assert seen["action"] is action
