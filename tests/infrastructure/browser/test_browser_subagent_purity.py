"""Tests for BrowserSubagent purity and voice isolation (INV-BROWSER-02 / INV-05)."""

from lca.infrastructure.browser.subagent import BrowserSubagent


def test_browser_subagent_has_no_voice():
    """INV-BROWSER-02: 浏览器子代理必须物理剔除声带发声工具 (send_message 严禁挂载)。"""
    agent = BrowserSubagent(agent_id="test_subagent_worker")
    tools = agent.get_tools()
    assert len(tools) > 0
    for tool in tools:
        assert getattr(tool, "name", "") != "send_message"
