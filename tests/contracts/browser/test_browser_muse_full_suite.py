"""Unit and contract tests for the complete Muse Browser 13 Tool Suite & Prompt Specification (ADR-0280 / Muse Spec)."""

from __future__ import annotations

import pytest

from lca.infrastructure.tools.browser import (
    BrowserCloseTaskTool,
    BrowserDeepResearchTool,
    BrowserFindTool,
    BrowserGetCaptchaPreferenceTool,
    BrowserListTasksTool,
    BrowserLookupCitationUrlTool,
    BrowserOpenTool,
    BrowserPeekTaskTool,
    BrowserSearchTool,
    BrowserSetCaptchaPreferenceTool,
    BrowserSpawnTaskTool,
    BrowserSteerTaskTool,
    BrowserTransferTaskTool,
    build_browser_tools,
)
from lca.infrastructure.tools.browser.task_store import (
    BrowserTaskRecord,
    BrowserTaskStore,
    SearchCitationStore,
    get_shared_citation_store,
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
async def test_muse_lightweight_search_no_provider_fails_closed(monkeypatch) -> None:
    """RA-147: 无可用搜索 provider 时 fail-closed，绝不伪造搜索结果。"""
    import lca.infrastructure.search.service.service as search_service

    monkeypatch.setattr(search_service, "any_search_provider_available", lambda: False)
    search_tool = BrowserSearchTool()
    obs = await search_tool.execute({"primary_query": "Python asyncio tutorial", "verticals": ["news"]})
    assert obs.success is False
    assert obs.error is not None
    assert "provider" in obs.error


@pytest.mark.asyncio
async def test_muse_lightweight_search_and_citation(monkeypatch) -> None:
    """RA-147: 搜索走真实搜索 seam；citation 解析返回真实 URL；未知引用 fail-closed。"""
    import lca.infrastructure.search.service.service as search_service
    from lca.infrastructure.search.models.models import SearchHit, SearchResponse

    monkeypatch.setattr(search_service, "any_search_provider_available", lambda: True)

    async def fake_web_search(query, *, topic=None, time_range=None):
        return SearchResponse(
            query=query,
            provider="fake",
            results=(
                SearchHit(
                    title="Asyncio Docs",
                    url="https://docs.python.org/3/library/asyncio.html",
                    content="asyncio tutorial",
                ),
            ),
        )

    monkeypatch.setattr(search_service, "web_search", fake_web_search)

    search_tool = BrowserSearchTool()
    obs = await search_tool.execute({"primary_query": "Python asyncio tutorial", "verticals": ["news"]})
    assert obs.success is True
    assert obs.payload is not None
    assert obs.payload["action_type"] == "search"
    results = obs.payload["details"]["results"]
    assert len(results) == 1
    assert results[0]["url"] == "https://docs.python.org/3/library/asyncio.html"
    assert "google.com/search" not in results[0]["url"]
    citation_id = results[0]["citation_id"]

    lookup_tool = BrowserLookupCitationUrlTool()
    lookup_obs = await lookup_tool.execute({"citation_id": citation_id})
    assert lookup_obs.success is True
    assert lookup_obs.payload["details"]["citation_id"] == citation_id
    assert (
        lookup_obs.payload["details"]["resolved_url"]
        == "https://docs.python.org/3/library/asyncio.html"
    )

    # 未搜索过的引用 → 诚实失败，不返回伪造 URL
    unknown_obs = await lookup_tool.execute({"citation_id": "cit_does_not_exist_1"})
    assert unknown_obs.success is False
    assert unknown_obs.error is not None


@pytest.mark.asyncio
async def test_muse_find_tool() -> None:
    """测试在当前打开页面中查找字符串。"""
    find_tool = BrowserFindTool()
    obs = await find_tool.execute({"query": "Login", "session_id": "sess_find_1"})
    assert obs.success is True
    assert obs.payload["action_type"] == "find"
    assert "Login" in obs.payload["text_content"]


@pytest.mark.asyncio
async def test_muse_spawn_task_fail_closed() -> None:
    """RA-149: 无真实异步派发后端（无 worker loop、无 handoff producer）时 fail-closed，不伪造"running"回执。"""
    spawn_tool = BrowserSpawnTaskTool()
    obs = await spawn_tool.execute({
        "task": "访问 muse.ai 并测试登录页面",
        "initial_url": "https://muse.ai",
        "session_id": "brw_muse_test_failclosed",
    })
    assert obs.success is False
    assert obs.error is not None
    assert "尚未实现" in obs.error
    assert obs.payload is None


@pytest.mark.asyncio
async def test_muse_task_lifecycle_steer_peek_close() -> None:
    """RA-149: 核心任务层生命周期（store 直接登记 -> steer -> peek -> list -> close）；spawn 工具本身已 fail-closed。"""
    from lca.contracts.atoms.ids.ids import new_id
    from lca.infrastructure.tools.browser.task_store import (
        BrowserTaskRecord,
        get_shared_task_store,
    )

    task_desc = "目标：访问 muse.ai 并测试登录页面；约束：不输入敏感密码；成功标准：看到登录按钮"
    task_id = new_id("btask")
    session_id = "brw_muse_test_1"
    store = get_shared_task_store()
    store.register_task(BrowserTaskRecord(
        task_id=task_id,
        task_description=task_desc,
        session_id=session_id,
        status="running",
        initial_url="https://muse.ai",
        current_url="https://muse.ai",
        title="Browser Task",
    ))
    store.add_timeline_step(task_id, "spawn", f"Task spawned: {task_desc[:80]}")
    assert task_id.startswith("btask_")

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
    """RA-147: 无真实 deep-research worker 后端时 fail-closed，不伪造"running"回执。"""
    research_tool = BrowserDeepResearchTool()
    obs = await research_tool.execute({
        "mission": "深度调研 2026 年最新开源 Agent 浏览器架构演进",
        "slug": "agent-browser-arch",
    })
    assert obs.success is False
    assert obs.error is not None
    assert "尚未实现" in obs.error


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


# =====================================================================
# RA-152: 浏览器 task-store 状态收敛
# =====================================================================


def test_ra152_browser_task_record_has_no_captcha_preference() -> None:
    """RA-152: BrowserTaskRecord.captcha_preference 死字段已删除。

    该字段全仓零读写（定义 1 次 + 零读取零写入）；真正的验证码状态只住在
    BrowserTaskStore._captcha_preferences（scope 键 all_tasks/site:/task:）。
    """
    record = BrowserTaskRecord(
        task_id="t1", task_description="d", session_id="s1"
    )
    assert not hasattr(record, "captcha_preference")


def test_ra152_captcha_preference_scope_priority() -> None:
    """RA-152: get_captcha_preference scope 优先级语义 task > site > all_tasks 不变。"""
    store = BrowserTaskStore()
    store.set_captcha_preference("ask", scope_kind="all_tasks", statement="global")
    store.set_captcha_preference("user_handles", scope_kind="site", scope_value="amazon.com", statement="s")
    store.set_captcha_preference("solve", scope_kind="task", scope_value="task-1", statement="t")

    assert store.get_captcha_preference()["choice"] == "ask"
    assert store.get_captcha_preference(site="amazon.com")["choice"] == "user_handles"
    assert store.get_captcha_preference(site="other.com")["choice"] == "ask"
    assert store.get_captcha_preference(site="amazon.com", task_id="task-1")["choice"] == "solve"
    assert store.get_captcha_preference(task_id="task-1")["choice"] == "solve"
    assert store.get_captcha_preference(site="amazon.com", task_id="task-9")["choice"] == "user_handles"

    # 默认值：什么都没设时为 solve
    assert BrowserTaskStore().get_captcha_preference()["choice"] == "solve"


def test_ra152_citation_store_lru_eviction() -> None:
    """RA-152: SearchCitationStore LRU 有界 —— 最久未用（写/读都刷新）先被驱逐。"""
    store = SearchCitationStore(max_entries=3)
    store.put("cit_a", title="A", url="https://a.example", snippet="sa")
    store.put("cit_b", title="B", url="https://b.example", snippet="sb")
    store.put("cit_c", title="C", url="https://c.example", snippet="sc")

    # 读刷新 recency：a 被访问后，b 成为最久未用
    assert store.get("cit_a") is not None
    store.put("cit_d", title="D", url="https://d.example", snippet="sd")

    assert len(store) == 3
    assert store.get("cit_b") is None  # 最久未用被驱逐
    assert store.get("cit_a")["url"] == "https://a.example"
    assert store.get("cit_c")["url"] == "https://c.example"
    assert store.get("cit_d")["url"] == "https://d.example"

    # 同 id 重复写入刷新且不膨胀
    store.put("cit_d", title="D2", url="https://d2.example", snippet="sd2")
    assert len(store) == 3
    assert store.get("cit_d")["title"] == "D2"


def test_ra152_citation_cache_lives_in_task_store_seam() -> None:
    """RA-152: _RECENT_SEARCH_RESULTS 模块全局已收敛进 task store seam。

    搜索写 / 引用读经共享 SearchCitationStore；tools 模块不再持有该全局。
    """
    import lca.infrastructure.tools.browser.tools as tools_module

    assert not hasattr(tools_module, "_RECENT_SEARCH_RESULTS")
    store = get_shared_citation_store()
    store.clear()
    store.put("cit_seam_1", title="T", url="https://seam.example/x", snippet="s")
    assert store.get("cit_seam_1")["url"] == "https://seam.example/x"
    store.clear()


# =====================================================================
# RA-153: "已在真实浏览器中打开"断言过 has_page 门
# =====================================================================


class _Ra153FakeDriver:
    """RA-153: 可控 liveness 的假 driver —— 复现 resilient（无 page）/ live 两种会话。"""

    def __init__(self, *, live: bool) -> None:
        self._live = live

    def has_page(self, session_id: str) -> bool:
        return self._live

    async def get_session(self, session_id: str):
        return None

    async def create_session(self, session_id: str, initial_url: str = "about:blank"):
        from lca.contracts.models.browser.stream import BrowserSessionStatus, BrowserSessionSummary

        return BrowserSessionSummary(
            session_id=session_id,
            run_id="run-ra153",
            url=initial_url,
            title="Example Page",
            status=BrowserSessionStatus.IDLE,
            viewport_width=1280,
            viewport_height=800,
            has_active_stream=False,
        )

    async def navigate(self, session_id: str, url: str):
        raise AssertionError("no pre-existing session in this fake")

    async def extract_text(self, session_id: str) -> str:
        return "visible body text" if self._live else ""


@pytest.mark.asyncio
async def test_ra153_open_tool_no_live_page_honest_wording() -> None:
    """RA-153: resilient 会话（无 live page）时工具绝不宣称"已在真实浏览器中打开"。

    success 语义：resilient 是合法部署状态（无 Chromium 也不崩溃），
    这不是错误 —— success=True，但措辞必须诚实，details.live_page=False 机器可判。
    """
    tool = BrowserOpenTool(driver=_Ra153FakeDriver(live=False))
    obs = await tool.execute({"url": "https://example.com"})
    assert obs.success is True
    text = obs.payload["text_content"]
    assert "已在真实浏览器中" not in text
    assert "session created, no live page" in text
    assert obs.payload["details"]["live_page"] is False
    assert "[widget:browser_preview" not in text  # 无页面可预览，不挂卡片


@pytest.mark.asyncio
async def test_ra153_open_tool_live_page_keeps_real_open_wording() -> None:
    """RA-153: 有 live page 时原有"真实浏览器打开"措辞与预览卡片保持不变。"""
    tool = BrowserOpenTool(driver=_Ra153FakeDriver(live=True))
    obs = await tool.execute({"url": "https://example.com"})
    assert obs.success is True
    text = obs.payload["text_content"]
    assert "已在真实浏览器中打开页面" in text
    assert obs.payload["details"]["live_page"] is True
    assert "[widget:browser_preview" in text


@pytest.mark.asyncio
async def test_ra153_navigate_goto_failure_no_fabricated_title() -> None:
    """RA-153: driver.navigate() 里 page.goto 失败后不再伪造 "Navigated Page" 标题。"""
    from lca.contracts.models.browser.stream import BrowserSessionStatus, BrowserSessionSummary
    from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver

    driver = PlaywrightCDPDriver()
    sid = "ra153-goto-fail"
    driver._sessions[sid] = BrowserSessionSummary(
        session_id=sid,
        run_id="run-ra153",
        url="https://example.com",
        title="Old Title",
        status=BrowserSessionStatus.IDLE,
        viewport_width=1280,
        viewport_height=800,
        has_active_stream=False,
    )

    class _FailingPage:
        async def goto(self, url, **kwargs):
            raise RuntimeError("net::ERR_CONNECTION_REFUSED")

    driver._pages[sid] = _FailingPage()
    summary = await driver.navigate(sid, "https://example.com/other")
    # goto 失败：保留导航前的已有标题，不伪造 "Navigated Page"
    assert summary.title == "Old Title"
    assert summary.title != "Navigated Page"
    assert summary.url == "https://example.com/other"


@pytest.mark.asyncio
async def test_ra158_open_tool_integer_url_id_fails_closed() -> None:
    """RA-158: 整数 url_id（页面 ID 形态）必须 fail-closed，绝不能 str() 后导航到 https://5 并谎报成功。"""
    tool = BrowserOpenTool(driver=_Ra153FakeDriver(live=True))
    obs = await tool.execute({"url_id": 5})
    assert obs.success is False
    assert "url_id" in (obs.error or "")


@pytest.mark.asyncio
async def test_ra158_open_tool_outlink_idx_and_line_start_fail_closed() -> None:
    """RA-158: schema 声明但实现不支持的 outlink_idx/line_start 必须 fail-closed，不能静默忽略。"""
    tool = BrowserOpenTool(driver=_Ra153FakeDriver(live=True))
    obs = await tool.execute({"url": "https://example.com", "outlink_idx": 1})
    assert obs.success is False
    assert "outlink_idx" in (obs.error or "")
    obs2 = await tool.execute({"url": "https://example.com", "line_start": 10})
    assert obs2.success is False
    assert "line_start" in (obs2.error or "")


@pytest.mark.asyncio
async def test_ra158_open_tool_url_shaped_url_id_still_honored() -> None:
    """RA-158: url_id 本身是 URL 形态时沿用旧路径（向后兼容），裸域名照旧补 https://。"""
    tool = BrowserOpenTool(driver=_Ra153FakeDriver(live=True))
    obs = await tool.execute({"url_id": "https://example.com"})
    assert obs.success is True
    assert obs.payload["url"] == "https://example.com"
    obs2 = await tool.execute({"url_id": "muse.ai"})
    assert obs2.success is True
    assert obs2.payload["url"] == "https://muse.ai"


@pytest.mark.asyncio
async def test_ra158_lookup_citation_url_id_fails_closed() -> None:
    """RA-158: browser_lookup_citation_url 的 url_id 声明了但从不读取，必须 fail-closed。"""
    tool = BrowserLookupCitationUrlTool()
    obs = await tool.execute({"citation_id": "c1", "url_id": 7})
    assert obs.success is False
    assert "url_id" in (obs.error or "")


@pytest.mark.asyncio
async def test_ra158_steer_screenshot_request_declared_not_silently_ignored() -> None:
    """RA-158: steer 的 user_requested_screenshot 不支持——指令照常受理，但 details 必须诚实声明未处理。"""
    from lca.contracts.atoms.ids.ids import new_id
    from lca.infrastructure.tools.browser.task_store import (
        BrowserTaskRecord,
        get_shared_task_store,
    )

    task_id = new_id("btask")
    store = get_shared_task_store()
    store.register_task(BrowserTaskRecord(
        task_id=task_id,
        task_description="RA-158 steer 截图声明测试",
        session_id="brw_ra158",
        status="running",
        initial_url="https://example.com",
        current_url="https://example.com",
        title="RA-158",
    ))
    tool = BrowserSteerTaskTool()
    obs = await tool.execute({
        "browser_task_id": task_id,
        "task": "继续",
        "user_requested_screenshot": True,
    })
    assert obs.success is True
    assert obs.payload["details"]["status"] == "running"
    assert obs.payload["details"]["user_requested_screenshot"] == "unsupported_ignored"
    # 不带该参数时 details 里不应出现该键
    obs2 = await tool.execute({"browser_task_id": task_id, "task": "继续"})
    assert "user_requested_screenshot" not in obs2.payload["details"]
