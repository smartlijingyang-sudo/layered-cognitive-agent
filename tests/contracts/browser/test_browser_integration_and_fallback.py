"""Tests for Muse Browser Integration, Tools, DeferPolicy, and Widget Fallback (ADR-0280)."""

from __future__ import annotations

import pytest

from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver
from lca.infrastructure.tool_defer.policy import (
    DEFAULT_NAMESPACE_DESCRIPTIONS,
    STANDARD_NAMESPACES,
    DeferPolicy,
)
from lca.infrastructure.tools.browser.tools import (
    BrowserCloseTool,
    BrowserOpenTool,
)
from lca.infrastructure.tools.default.set import build_default_tools
from lca.runtime.session.run_session_writer import (
    ensure_browser_widget_in_assistant_message,
    extract_pending_browser_widgets_from_events,
)


def test_defer_policy_browser_namespace() -> None:
    """验证 browser 命名空间在 DeferPolicy 中注册且文案准确。"""
    assert "browser" in STANDARD_NAMESPACES
    assert "browser" in DEFAULT_NAMESPACE_DESCRIPTIONS
    assert "Chromium" in DEFAULT_NAMESPACE_DESCRIPTIONS["browser"]

    policy = DeferPolicy.default()
    assert "browser" in policy.known_namespaces
    # browser 属于按需加载的 deferred namespace
    assert "browser" not in policy.eager_namespaces


@pytest.mark.asyncio
async def test_browser_navigate_and_open_tool_execution() -> None:
    """验证浏览器打开与导航工具能输出带 widget_tag 的结构化结果。"""
    driver = PlaywrightCDPDriver()
    tool = BrowserOpenTool(driver=driver)
    assert tool.name == "browser_open"
    assert tool.namespace == "browser"

    obs = await tool.execute({"url": "muse.ai", "session_id": "test_brw_001"})
    assert obs.success is True
    assert obs.payload is not None
    assert obs.payload["session_id"] == "test_brw_001"
    assert "https://muse.ai" in obs.payload["url"]
    assert "[widget:browser_preview?sessionId=test_brw_001" in obs.payload["widget_tag"]
    assert "agent_running" in obs.payload["widget_tag"]

    # 验证导航已在驱动中生成 Session
    session = await driver.get_session("test_brw_001")
    assert session is not None
    assert session.session_id == "test_brw_001"

    # 测试通过 browser_close 关闭
    close_tool = BrowserCloseTool(driver=driver)
    close_obs = await close_tool.execute({"session_id": "test_brw_001"})
    assert close_obs.success is True
    assert await driver.get_session("test_brw_001") is None


def test_default_tools_include_browser() -> None:
    """验证系统默认工具集注入了 browser 域的完整能力。"""
    tools = build_default_tools()
    tool_names = {t.name for t in tools}
    browser_tools = [t for t in tools if getattr(t, "namespace", "") == "browser"]

    assert "browser_open" in tool_names
    assert "browser_navigate" in tool_names
    assert "browser_click" in tool_names
    assert "browser_screenshot" in tool_names
    assert "browser_close" in tool_names
    assert len(browser_tools) >= 5


def test_browser_widget_deterministic_fallback() -> None:
    """验证 ADR-0280 网关层确定性保底投影（漏写时自动补齐，已有则不重复）。"""

    # 模拟 tool_result 事件中带有 browser_preview 标签
    class MockEvent:
        def __init__(self, event_type: str, data: dict) -> None:
            self.type = event_type
            self.data = data

    events = [
        MockEvent(
            "surface/tool_result",
            {
                "content": "已打开页面：[widget:browser_preview?sessionId=brw_999&url=https%3A%2F%2Fmuse.ai&title=Muse&status=agent_running]",
                "tool_call_id": "call_1",
            },
        )
    ]

    pending = extract_pending_browser_widgets_from_events(events)
    assert len(pending) == 1
    assert pending[0]["sessionId"] == "brw_999"

    # Case 1: 模型回复正文漏写了 widget，保底追加
    raw_content = "我已经帮你打开了 muse.ai 网站。"
    augmented = ensure_browser_widget_in_assistant_message(raw_content, pending)
    assert "[widget:browser_preview?sessionId=brw_999" in augmented
    assert augmented.startswith("我已经帮你打开了 muse.ai 网站。")

    # Case 2: 模型回复正文已包含该 sessionId，不重复追加
    already_has = "这是网页预览：\n[widget:browser_preview?sessionId=brw_999&url=https://muse.ai]"
    not_duplicated = ensure_browser_widget_in_assistant_message(already_has, pending)
    assert not_duplicated == already_has
