"""Unit and contract tests for the complete Muse Browser 13 Tool Suite & Prompt Specification (ADR-0280 / Muse Spec)."""

from __future__ import annotations

import pytest

from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver
from lca.infrastructure.tools.browser import (
    BrowserCloseTaskTool,
    BrowserDeepResearchTool,
    BrowserFindTool,
    BrowserGetCaptchaPreferenceTool,
    BrowserListTasksTool,
    BrowserLookupCitationUrlTool,
    BrowserPeekTaskTool,
    BrowserSearchTool,
    BrowserSetCaptchaPreferenceTool,
    BrowserSpawnTaskTool,
    BrowserSteerTaskTool,
    BrowserTransferTaskTool,
    build_browser_tools,
)
from lca.infrastructure.tools.default.set import build_default_tools


def test_muse_13_tools_registered_in_build_browser_tools() -> None:
    """验证 Muse 13 大核心工具 + 兼容工具完整导出且命名空间均为 browser。"""
    tools = build_browser_tools()
    tool_map = {t.name: t for t in tools}

    expected_muse_tools = [
        # 轻量层 (4)
        "browser_search",
        "browser_open",
        "browser_find",
        "browser_lookup_citation_url",
        # 实时任务层 (6)
        "browser_spawn_task",
        "browser_steer_task",
        "browser_list_tasks",
        "browser_peek_task",
        "browser_close_task",
        "browser_transfer_task",
        # CAPTCHA 偏好 (2)
        "browser_set_captcha_preference",
        "browser_get_captcha_preference",
        # 研究层 (1)
        "browser_deep_research",
    ]

    for tool_name in expected_muse_tools:
        assert tool_name in tool_map, f"Missing Muse tool: {tool_name}"
        assert tool_map[tool_name].namespace == "browser"

    # 验证兼容工具
    for compat in ["browser_navigate", "browser_click", "browser_screenshot", "browser_close"]:
        assert compat in tool_map
        assert tool_map[compat].namespace == "browser"


def test_default_tools_exports_all_muse_tools() -> None:
    """验证全局 build_default_tools 完整挂载 Muse 工具集。"""
    tools = build_default_tools()
    names = {t.name for t in tools}
    assert "browser_spawn_task" in names
    assert "browser_steer_task" in names
    assert "browser_search" in names
    assert "browser_transfer_task" in names
    assert "browser_deep_research" in names


@pytest.mark.asyncio
async def test_muse_lightweight_search_and_citation() -> None:
    """测试轻量层搜索与引用解析（无需启动真实浏览器）。"""
    search_tool = BrowserSearchTool()
    obs = await search_tool.execute({"primary_query": "Python asyncio tutorial", "verticals": ["news"]})
    assert obs.success is True
    assert obs.payload is not None
    assert obs.payload["action_type"] == "search"
    results = obs.payload["details"]["results"]
    assert len(results) > 0
    citation_id = results[0]["citation_id"]

    lookup_tool = BrowserLookupCitationUrlTool()
    lookup_obs = await lookup_tool.execute({"citation_id": citation_id})
    assert lookup_obs.success is True
    assert lookup_obs.payload["details"]["citation_id"] == citation_id


@pytest.mark.asyncio
async def test_muse_find_tool() -> None:
    """测试在当前打开页面中查找字符串。"""
    find_tool = BrowserFindTool()
    obs = await find_tool.execute({"query": "Login", "session_id": "sess_find_1"})
    assert obs.success is True
    assert obs.payload["action_type"] == "find"
    assert "Login" in obs.payload["text_content"]


@pytest.mark.asyncio
async def test_muse_task_lifecycle_spawn_steer_peek_close() -> None:
    """测试核心任务层生命周期：spawn -> steer -> peek -> list -> close。"""
    driver = PlaywrightCDPDriver()
    spawn_tool = BrowserSpawnTaskTool(driver=driver)

    task_desc = "目标：访问 muse.ai 并测试登录页面；约束：不输入敏感密码；成功标准：看到登录按钮"
    spawn_obs = await spawn_tool.execute({
        "task": task_desc,
        "initial_url": "https://muse.ai",
        "session_id": "brw_muse_test_1",
    })
    assert spawn_obs.success is True
    task_id = spawn_obs.payload["browser_task_id"]
    session_id = spawn_obs.payload["session_id"]
    assert task_id.startswith("btask_")
    assert session_id == "brw_muse_test_1"
    assert "[widget:browser_preview" in spawn_obs.payload["widget_tag"]

    # 验证 peek_task
    peek_tool = BrowserPeekTaskTool()
    peek_obs = await peek_tool.execute({"browser_task_id": task_id})
    assert peek_obs.success is True
    assert peek_obs.payload["details"]["browser_task_id"] == task_id
    assert len(peek_obs.payload["details"]["timeline"]) >= 1

    # 验证 steer_task (纠偏/追加指令)
    steer_tool = BrowserSteerTaskTool()
    steer_obs = await steer_tool.execute({
        "browser_task_id": task_id,
        "task": "点击右上角 Sign In 按钮",
        "wallet_payment": {"provider": "apple_pay", "payment_method_id": "pm_123"},
    })
    assert steer_obs.success is True
    assert steer_obs.payload["details"]["status"] == "running"

    # 验证 list_tasks
    list_tool = BrowserListTasksTool()
    list_obs = await list_tool.execute({"status": "running"})
    assert list_obs.success is True
    task_ids = [t["browser_task_id"] for t in list_obs.payload["details"]["tasks"]]
    assert task_id in task_ids

    # 验证 close_task
    close_tool = BrowserCloseTaskTool()
    close_obs = await close_tool.execute({"browser_task_id": task_id, "reason": "测试完成"})
    assert close_obs.success is True

    # 验证关闭后状态
    peek_after = await peek_tool.execute({"browser_task_id": task_id})
    assert peek_after.payload["details"]["status"] == "closed"


@pytest.mark.asyncio
async def test_muse_task_transfer_takeover() -> None:
    """测试人机协作接管与转回（human_takeover）。"""
    transfer_tool = BrowserTransferTaskTool()
    obs = await transfer_tool.execute({
        "session_id": "brw_takeover_1",
        "target": "human_takeover",
        "reason": "需要用户进行短信二次验证",
    })
    assert obs.success is True
    assert obs.payload["details"]["target"] == "human_takeover"
    assert "status=human_takeover" in obs.payload["widget_tag"]


@pytest.mark.asyncio
async def test_muse_captcha_preference_persistence() -> None:
    """测试验证码独立偏好设置与读取契约。"""
    set_tool = BrowserSetCaptchaPreferenceTool()
    set_obs = await set_tool.execute({
        "choice": "user_handles",
        "scope": {"kind": "site", "value": "amazon.com"},
        "user_statement": "遇到亚马逊验证码请让我自己接管",
    })
    assert set_obs.success is True

    get_tool = BrowserGetCaptchaPreferenceTool()
    get_obs = await get_tool.execute({"site": "amazon.com"})
    assert get_obs.success is True
    assert get_obs.payload["details"]["choice"] == "user_handles"

    # 默认值应为 solve
    default_obs = await get_tool.execute({"site": "unknown-site.org"})
    assert default_obs.payload["details"]["choice"] == "solve"


@pytest.mark.asyncio
async def test_muse_deep_research_launch() -> None:
    """测试深度研究任务派发与回执。"""
    research_tool = BrowserDeepResearchTool()
    obs = await research_tool.execute({
        "mission": "深度调研 2026 年最新开源 Agent 浏览器架构演进",
        "slug": "agent-browser-arch",
    })
    assert obs.success is True
    assert obs.payload["details"]["slug"] == "agent-browser-arch"
    assert obs.payload["details"]["status"] == "running"
    assert "已启动深度研究任务" in obs.payload["text_content"]


def test_muse_constitution_contract_in_templates() -> None:
    """验证智能体宪法模板中完整写入了 Muse 浏览器环境声明、三条铁律与路由决策树。"""
    from pathlib import Path
    template_path = Path("lca/plugins/assistant/templates/CONSTITUTION.md")
    assert template_path.exists()
    content = template_path.read_text(encoding="utf-8")

    assert "Muse Browser System Contract" in content
    assert "Three Calling Iron Rules" in content
    assert "Asynchronous Execution" in content
    assert "Task Self-Contained" in content
    assert "Permission Convergence" in content
    assert "Browser and Source Routing Rules" in content
    assert "browser_spawn_task" in content
    assert "browser_open" in content
    assert "browser_search" in content
    assert "browser_deep_research" in content
