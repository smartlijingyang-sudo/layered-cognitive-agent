"""Complete Muse Browser Tool Suite for Agent & Subagent (ADR-0248 §5.3 / ADR-0280 / Muse Browser Spec).

Implements all 13 Muse Browser tools across 4 architectural layers:
1. Lightweight Layer (4 tools): browser_search, browser_open, browser_find, browser_lookup_citation_url
2. Live Chromium Task Layer (6 tools): browser_spawn_task, browser_steer_task, browser_list_tasks, browser_peek_task, browser_close_task, browser_transfer_task
3. CAPTCHA Preferences (2 tools): browser_set_captcha_preference, browser_get_captcha_preference
4. Research Layer (1 tool): browser_deep_research
Plus legacy/convenience tools: browser_navigate, browser_click, browser_screenshot, browser_close
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.browser.models import BrowserActionResult, BrowserActionType
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.infrastructure.tools.browser.driver_tool import (
    _DriverInjectedTool,
    browser_preview_widget_tag,
)
from lca.infrastructure.tools.browser.task_store import (
    get_shared_citation_store,
    get_shared_task_store,
)

if TYPE_CHECKING:
    from lca.infrastructure.browser.arbitration import BrowserArbitrationEngine
    from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    """自动补齐缺少协议的 URL，默认补齐 https://。"""
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://", "about:", "chrome://")):
        return f"https://{cleaned}"
    return cleaned


# =====================================================================
# 1. 轻量层（4 个工具，无真实浏览器或纯文本抓取，低成本、快速）
# =====================================================================

class BrowserSearchTool(Tool):
    """文本搜索工具（Muse 轻量层）。只做信息发现，不启动真实浏览器。"""

    name: ClassVar[str] = "browser_search"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "纯文本网页与信息搜索。只做信息检索发现，不打开真实浏览器。"
        "URL、链接、裸域名不是搜索 query。通用搜索结果可能过期，不证明实时库存/价格/余票状态。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "primary_query": {
                "type": ["string", "object"],
                "description": "搜索关键词（字符串），或包含 query 和可选 language_code 的对象",
            },
            "verticals": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["news", "sports", "weather", "finance", "datetime"],
                },
                "maxItems": 1,
                "description": "可选垂类筛选，最多指定一个",
            },
        },
        "required": ["primary_query"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 20

    async def execute(self, args: dict[str, Any]) -> Observation:
        raw_query = args.get("primary_query")
        if isinstance(raw_query, dict):
            query = str(raw_query.get("query", ""))
        else:
            query = str(raw_query or "")
        query = query.strip()
        if not query:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error="搜索 query 为空",
            )

        verticals = args.get("verticals") or []
        topic = str(verticals[0]) if verticals else None

        # RA-147: 走真实搜索 seam；无可用 provider 时 fail-closed，绝不伪造结果。
        # 函数内导入：避免 infrastructure.search 与 tools.browser 的导入时循环。
        from lca.infrastructure.search.service.service import (
            any_search_provider_available,
            web_search,
        )

        if not any_search_provider_available():
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error="未配置可用的搜索 provider，无法执行网页搜索",
            )
        try:
            response = await web_search(query, topic=topic)
        except Exception as exc:
            logger.warning("[BrowserSearchTool] web_search failed: %s", exc)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"网页搜索执行异常: {exc}",
            )
        if not response.ok:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"网页搜索失败: {response.error or '无结果'}",
            )

        search_id = new_id("bsearch")
        citation_store = get_shared_citation_store()
        results = []
        for i, hit in enumerate(response.results, start=1):
            citation_id = f"cit_{search_id}_{i}"
            snippet = (hit.content or "")[:400]
            # RA-152: 引用缓存走 task store seam 的 SearchCitationStore（LRU 有界），
            # 不再是模块全局无界 dict。
            citation_store.put(citation_id, title=hit.title, url=hit.url, snippet=snippet)
            results.append(
                {
                    "citation_id": citation_id,
                    "title": hit.title,
                    "snippet": snippet,
                    "url": hit.url,
                }
            )

        text_content = (
            f"搜索完成 [{search_id}]（provider: {response.provider}）："
            f"找到 {len(results)} 条相关线索。\n"
        )
        for r in results:
            text_content += f"- [{r['citation_id']}] {r['title']} ({r['url']}): {r['snippet']}\n"

        res = BrowserActionResult(
            action_type=BrowserActionType.SEARCH,
            success=True,
            text_content=text_content,
            details={
                "search_id": search_id,
                "query": query,
                "verticals": verticals,
                "provider": response.provider,
                "results": results,
            },
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


class BrowserOpenTool(_DriverInjectedTool):
    """抓页面文本 / 在真实浏览器中打开（Muse 轻量与实时双模入口）。"""

    name: ClassVar[str] = "browser_open"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "在真实浏览器中打开网页或通过原样 URL / 搜索引用抓取页面文本并展示实时预览卡片。"
        "字面 URL 必须原样复制自工具返回或用户消息，禁止猜、禁止拼接。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "目标网页 URL 或域名（例如 'https://news.ycombinator.com' 或 'muse.ai'）",
            },
            "url_id": {
                "type": ["string", "integer"],
                "description": "可选：此前 search 或 open 返回的页面 ID 或搜索会话 ID",
            },
            "outlink_idx": {
                "type": "integer",
                "description": "可选：选择搜索结果或页内真实链接序号",
            },
            "line_start": {
                "type": "integer",
                "description": "可选：翻页续读起始行号",
            },
            "session_id": {
                "type": "string",
                "description": "可选：指定复用的浏览器会话 ID。如果不提供将自动分配新会话",
            },
        },
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def validate(self, args: dict[str, Any]) -> str | None:
        if not args.get("url") and not args.get("url_id"):
            return "url 或 url_id 至少提供一项"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return Observation(observation_id=new_id("obs"), success=False, payload=None, error=err)

        raw_url = str(args.get("url") or args.get("url_id") or "about:blank")
        url = _normalize_url(raw_url)
        session_id = str(args.get("session_id") or new_id("brw"))

        driver = self._get_driver()
        try:
            existing = await driver.get_session(session_id)
            if existing is not None:
                summary = await driver.navigate(session_id=session_id, url=url)
            else:
                summary = await driver.create_session(session_id=session_id, initial_url=url)
        except Exception as e:
            logger.warning("[BrowserOpenTool] Browser driver error: %s", e)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload={"session_id": session_id, "url": url, "error": str(e)},
                error=f"浏览器打开失败: {e}",
            )

        title = summary.title or "Web Page"
        final_url = summary.url or url
        # RA-153: "已在真实浏览器中打开页面"断言要过 has_page 门 —— resilient
        # 会话（session record 无 page）是 driver 层的合法状态，但工具层绝不
        # 在此状态下宣称真实打开。
        live_page = driver.has_page(session_id)
        if live_page:
            widget_tag = browser_preview_widget_tag(
                session_id, final_url, title, "agent_running"
            )
            try:
                page_text = await driver.extract_text(session_id)
            except Exception as e:
                logger.warning("[BrowserOpenTool] extract_text error: %s", e)
                page_text = ""
            text_content = f"已在真实浏览器中打开页面：{title} ({final_url})\n\n"
            if page_text:
                text_content += f"页面内容预览：\n{page_text[:800]}\n\n"
            text_content += widget_tag
        else:
            # 无 live page：诚实措辞，不挂预览卡片（没有页面可预览）。
            # success 语义：resilient 模式是合法部署状态（无 Chromium 也不崩溃），
            # 这不是错误；调用方凭 text_content 与 details.live_page 区分。
            widget_tag = ""
            text_content = (
                f"浏览器会话已创建（session {session_id}），但当前无可用的真实浏览器页面 "
                f"(session created, no live page)；目标：{title} ({final_url})。\n"
            )

        res = BrowserActionResult(
            action_type=BrowserActionType.NAVIGATE,
            success=True,
            session_id=session_id,
            url=final_url,
            title=title,
            text_content=text_content,
            details={"live_page": live_page},
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={**res.model_dump(), "widget_tag": widget_tag},
        )


class BrowserFindTool(_DriverInjectedTool):
    """在已打开的页面内查找字符串（Muse 轻量层）。"""

    name: ClassVar[str] = "browser_find"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "在当前打开的浏览器页面内精确查找匹配字符串。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "要查找的目标字符串"},
            "session_id": {"type": "string", "description": "目标浏览器会话 ID"},
            "case_sensitive": {"type": "boolean", "description": "是否区分大小写，默认 false"},
        },
        "required": ["query"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 15

    async def execute(self, args: dict[str, Any]) -> Observation:
        query = str(args.get("query", ""))
        session_id = str(args.get("session_id") or "")
        case_sensitive = bool(args.get("case_sensitive", False))
        matches = await self._get_driver().find_text(
            session_id, query, case_sensitive=case_sensitive
        )
        if matches > 0:
            text_content = f"已在页面检索 '{query}'，找到 {matches} 处匹配。"
        else:
            text_content = f"页面中未找到 '{query}' 的匹配。"
        res = BrowserActionResult(
            action_type=BrowserActionType.FIND,
            success=True,
            session_id=session_id or None,
            text_content=text_content,
            details={
                "query": query,
                "matches_count": matches,
                "case_sensitive": case_sensitive,
            },
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


class BrowserLookupCitationUrlTool(Tool):
    """将搜索结果索引解析为真实 URL 与标题（Muse 轻量层）。"""

    name: ClassVar[str] = "browser_lookup_citation_url"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "把某次 search 返回的 citation_id 解析为真实 URL 和标题。不解决访问问题。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "citation_id": {"type": ["string", "integer"], "description": "搜索结果的引用 ID"},
            "url_id": {"type": ["string", "integer"], "description": "可选搜索会话 ID"},
        },
        "required": ["citation_id"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 10

    async def execute(self, args: dict[str, Any]) -> Observation:
        cid = str(args.get("citation_id") or "")
        if not cid:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error="citation_id 必填",
            )
        # RA-147: 只解析真实搜索产生过的引用；未知引用 fail-closed，
        # 绝不返回伪造 URL。
        hit = get_shared_citation_store().get(cid)
        if hit is None:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"未找到引用 {cid}：请先用 browser_search 搜索后再解析",
            )
        res = BrowserActionResult(
            action_type=BrowserActionType.SEARCH,
            success=True,
            text_content=f"Citation {cid} resolved.",
            details={"citation_id": cid, "resolved_url": hit["url"], "title": hit["title"]},
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


# =====================================================================
# 2. 实时浏览器任务层（6 个核心工具，异步委托、任务自包含、权限收敛）
# =====================================================================

class BrowserSpawnTaskTool(_DriverInjectedTool):
    """浏览器异步任务派发工具：派发后端尚未实现，调用 fail-closed（Muse 核心任务层占位）。"""

    name: ClassVar[str] = "browser_spawn_task"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "浏览器异步任务派发工具（任务书参数契约保留）。"
        "【未实现】异步派发后端尚未实现：调用将返回错误，不会启动后台任务；"
        "不要承诺后台执行或 handoff 结果回流。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "完整自包含的任务书（目标、站点、已知条件、步骤约束、成功标准、停止条件）",
            },
            "initial_url": {
                "type": "string",
                "description": "已知首跳 URL（例如 'https://github.com' 或 'muse.ai'），没有才省略",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选：最多 64 个 workspace 文件，作为不透明上传授权",
            },
            "user_requested_screenshot": {
                "type": "boolean",
                "description": "用户明确要求截图时才设为 true",
            },
            "session_id": {
                "type": "string",
                "description": "可选：绑定的浏览器会话 ID",
            },
        },
        "required": ["task"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    default_timeout_s: ClassVar[int] = 30

    async def execute(self, args: dict[str, Any]) -> Observation:
        # RA-149: 没有真实的异步派发后端（无 worker loop、无 handoff producer，
        # task_description 全仓零消费者），诚实 fail-closed。绝不返回"已派发/running"的伪造回执。
        task_text = str(args.get("task") or "")
        logger.warning(
            "[BrowserSpawnTaskTool] async spawn backend not implemented (task=%r)",
            task_text[:80],
        )
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error="浏览器异步任务派发尚未实现：browser_spawn_task 当前无法派发真实后台任务（无 worker 后端、无 handoff 回流接线）",
        )



class BrowserSteerTaskTool(Tool):
    """给已存在的任务发下一条指令 / 纠偏 / 传批准（Muse 核心任务层）。"""

    name: ClassVar[str] = "browser_steer_task"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "给已存在的任务发下一条指令。只写变化或下一步，禁止复述整个任务书（避免重复执行）。"
        "若任务处于 parked（等待用户验证码/登录/支付批准）状态，此调用将带答复恢复执行。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "browser_task_id": {"type": "string", "description": "目标任务 ID"},
            "task": {"type": "string", "description": "下一步指令、纠偏或用户提供的数据（只写增量）"},
            "wallet_payment": {
                "type": "object",
                "description": "可选：用户批准购买后传入的钱包/支付批准参数",
            },
            "user_requested_screenshot": {"type": "boolean", "description": "追加或撤回截图需求"},
        },
        "required": ["browser_task_id", "task"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    default_timeout_s: ClassVar[int] = 30

    async def execute(self, args: dict[str, Any]) -> Observation:
        task_id = str(args["browser_task_id"])
        instruction = str(args["task"])
        wallet = args.get("wallet_payment")

        task_store = get_shared_task_store()
        task = task_store.get_task(task_id)
        if not task:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"未找到浏览器任务 {task_id}",
            )

        task.status = "running"
        if wallet:
            task.payment_approved = True
            task_store.add_timeline_step(task_id, "payment_approved", f"Payment approved via wallet: {wallet}")

        task_store.add_timeline_step(task_id, "steer", instruction)

        res = BrowserActionResult(
            action_type=BrowserActionType.STEER,
            success=True,
            session_id=task.session_id,
            task_id=task_id,
            text_content=f"已向任务 {task_id} 注入指令，任务已恢复运行。",
            details={"browser_task_id": task_id, "status": "running", "instruction": instruction},
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


class BrowserListTasksTool(Tool):
    """只读列出本会话的浏览器任务列表（Muse 核心任务层）。"""

    name: ClassVar[str] = "browser_list_tasks"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "列出当前会话的浏览器任务（进行中在前）。只读，用于回答用户状态或获取 task_id，禁止用它循环轮询等待。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["running", "parked", "succeeded", "failed", "blocked", "closed", "human_takeover"],
                "description": "可选状态过滤",
            },
        },
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 10

    async def execute(self, args: dict[str, Any]) -> Observation:
        status_filter = args.get("status")
        task_store = get_shared_task_store()
        tasks = task_store.list_tasks(status=status_filter)
        task_dicts = [t.to_dict() for t in tasks]

        text_content = f"当前浏览器任务列表（共 {len(tasks)} 个）：\n"
        for t in task_dicts:
            text_content += f"- `{t['browser_task_id']}` [{t['status']}] steps={t['step_count']} url={t['current_url']}\n"

        res = BrowserActionResult(
            action_type=BrowserActionType.EXTRACT_TEXT,
            success=True,
            text_content=text_content,
            details={"tasks": task_dicts, "total": len(tasks)},
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


class BrowserPeekTaskTool(Tool):
    """只读查看单个任务的详细时间线与当前页面状态（Muse 核心任务层）。"""

    name: ClassVar[str] = "browser_peek_task"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "查看单个任务的详细时间线（最近 40 条动作、当前 URL/标题、进度消息）。只读，回答浏览器在干嘛时使用。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "browser_task_id": {"type": "string", "description": "目标任务 ID"},
        },
        "required": ["browser_task_id"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 10

    async def execute(self, args: dict[str, Any]) -> Observation:
        task_id = str(args["browser_task_id"])
        task_store = get_shared_task_store()
        task = task_store.get_task(task_id)
        if not task:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"未找到浏览器任务 {task_id}",
            )

        recent_steps = task.timeline[-40:]
        text_content = (
            f"任务 {task_id} 详情：\n"
            f"- 状态：{task.status}\n"
            f"- 目标会话：{task.session_id}\n"
            f"- 当前页面：{task.title or 'Unknown'} ({task.current_url})\n"
            f"- 最近步骤（共 {len(recent_steps)} 条）：\n"
        )
        for s in recent_steps:
            text_content += f"  [{s['step_index']}] {s['action']}: {s['detail']}\n"

        res = BrowserActionResult(
            action_type=BrowserActionType.EXTRACT_TEXT,
            success=True,
            session_id=task.session_id,
            task_id=task_id,
            url=task.current_url,
            title=task.title,
            text_content=text_content,
            details={
                "browser_task_id": task_id,
                "status": task.status,
                "timeline": recent_steps,
            },
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


class BrowserCloseTaskTool(Tool):
    """终止浏览器任务，释放排位槽（Muse 核心任务层）。"""

    name: ClassVar[str] = "browser_close_task"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "终止指定的浏览器任务并释放排位槽。用于用户明确放弃或任务已完成。"
        "若只是修改需求，应使用 browser_steer_task 继续，无需 close 重开。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "browser_task_id": {"type": "string", "description": "要终止的任务 ID"},
            "reason": {"type": "string", "description": "可选关闭原因"},
        },
        "required": ["browser_task_id"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    default_timeout_s: ClassVar[int] = 10

    async def execute(self, args: dict[str, Any]) -> Observation:
        task_id = str(args["browser_task_id"])
        reason = args.get("reason") or "User requested close"
        task_store = get_shared_task_store()
        closed = task_store.close_task(task_id, reason=reason)

        res = BrowserActionResult(
            action_type=BrowserActionType.CLOSE,
            success=closed,
            task_id=task_id,
            text_content=f"浏览器任务 {task_id} 已终止：{reason}",
            details={"browser_task_id": task_id, "closed": closed, "reason": reason},
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


class BrowserTransferTaskTool(Tool):
    """接管浏览器控制权 / 人机协作接棒（Muse 核心任务层）。"""

    name: ClassVar[str] = "browser_transfer_task"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "在用户与 Agent 之间转移浏览器控制权。当 target 为 'human_takeover' 时，"
        "切换为人工接管模式并唤起右侧实时交互视口，由用户亲自操作；用户完成后可转回 agent。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "browser_task_id": {"type": "string", "description": "可选任务 ID"},
            "session_id": {"type": "string", "description": "可选浏览器会话 ID"},
            "target": {
                "type": "string",
                "enum": ["human_takeover", "agent"],
                "description": "接管目标：'human_takeover'（人工接管）或 'agent'（转回 AI）",
            },
            "reason": {"type": "string", "description": "可选接管原因"},
        },
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    default_timeout_s: ClassVar[int] = 15

    def __init__(
        self,
        arbitration_engine: BrowserArbitrationEngine | None = None,
    ) -> None:
        self._arbitration_engine = arbitration_engine

    def _get_arbitration(self) -> BrowserArbitrationEngine | None:
        if self._arbitration_engine is not None:
            return self._arbitration_engine
        try:
            from lca.infrastructure.browser.cdp_driver import get_shared_browser_driver

            return getattr(get_shared_browser_driver(), "arbitration_engine", None)
        except Exception:
            return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        target = str(args.get("target") or "human_takeover")
        task_id = args.get("browser_task_id")
        session_id = args.get("session_id") or "default"
        reason = str(args.get("reason") or "User takeover requested")

        task_store = get_shared_task_store()
        if task_id:
            task = task_store.get_task(task_id)
            if task:
                task.status = target
                session_id = task.session_id
                task_store.add_timeline_step(task_id, "transfer", f"Transfer to {target}: {reason}")

        # 驱动仲裁状态机：human_takeover 放行人工输入，agent 交还控制权给 AI。
        arbitration = self._get_arbitration()
        if arbitration is not None:
            if target == "human_takeover":
                arbitration.request_human_takeover(session_id, reason=reason)
            else:
                arbitration.release_to_agent(session_id)

        status_tag = "human_takeover" if target == "human_takeover" else "agent_running"
        widget_tag = browser_preview_widget_tag(session_id, "about:blank", "Live%20Browser", status_tag)
        text_content = (
            f"已将浏览器控制权切换为：**{target}**。\n"
            f"原因：{reason}\n\n"
            f"{widget_tag}"
        )

        res = BrowserActionResult(
            action_type=BrowserActionType.TRANSFER,
            success=True,
            session_id=session_id,
            task_id=str(task_id) if task_id else None,
            text_content=text_content,
            details={"target": target, "session_id": session_id, "status": status_tag},
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={**res.model_dump(), "widget_tag": widget_tag},
        )


# =====================================================================
# 3. CAPTCHA 偏好（2 个工具，持久化用户偏好，非 prompt 记忆）
# =====================================================================

class BrowserSetCaptchaPreferenceTool(Tool):
    """保存用户明确的验证码处理偏好（Muse 偏好规范）。"""

    name: ClassVar[str] = "browser_set_captcha_preference"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "保存用户明确要求的验证码处理偏好。choice 可选 solve（浏览器自解）、"
        "ask（遇到就问）、user_handles（用户接管）。默认 solve。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "choice": {
                "type": "string",
                "enum": ["solve", "ask", "user_handles"],
                "description": "偏好选择",
            },
            "scope": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["all_tasks", "site", "task"],
                        "description": "生效范围",
                    },
                    "value": {"type": "string", "description": "域名或 task_id"},
                },
                "required": ["kind"],
            },
            "user_statement": {
                "type": "string",
                "description": "用户原话逐字引用",
            },
        },
        "required": ["choice", "user_statement"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    default_timeout_s: ClassVar[int] = 10

    async def execute(self, args: dict[str, Any]) -> Observation:
        choice = str(args["choice"])
        user_statement = str(args["user_statement"])
        scope = args.get("scope") or {"kind": "all_tasks"}
        scope_kind = str(scope.get("kind", "all_tasks"))
        scope_value = scope.get("value")

        task_store = get_shared_task_store()
        task_store.set_captcha_preference(
            choice=choice,
            scope_kind=scope_kind,
            scope_value=scope_value,
            statement=user_statement,
        )

        text_content = f"已保存验证码处理偏好：{choice}（范围：{scope_kind}）。"
        res = BrowserActionResult(
            action_type=BrowserActionType.CAPTCHA_PREFERENCE,
            success=True,
            text_content=text_content,
            details={"choice": choice, "scope_kind": scope_kind, "scope_value": scope_value},
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


class BrowserGetCaptchaPreferenceTool(Tool):
    """读取当前权威验证码偏好（Muse 偏好规范）。"""

    name: ClassVar[str] = "browser_get_captcha_preference"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "读取指定网站或任务的当前权威验证码偏好设置。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "site": {"type": "string", "description": "可选网站域名（如 'amazon.com'）"},
            "task_id": {"type": "string", "description": "可选任务 ID"},
        },
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 10

    async def execute(self, args: dict[str, Any]) -> Observation:
        site = args.get("site")
        task_id = args.get("task_id")
        task_store = get_shared_task_store()
        pref = task_store.get_captcha_preference(site=site, task_id=task_id)

        res = BrowserActionResult(
            action_type=BrowserActionType.CAPTCHA_PREFERENCE,
            success=True,
            text_content=f"当前验证码偏好：{pref.get('choice')}（范围：{pref.get('scope_kind')}）",
            details=pref,
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


# =====================================================================
# 4. 研究层（1 个工具，深度调研，带来源与报告返回）
# =====================================================================

class BrowserDeepResearchTool(Tool):
    """派发隔离的深度研究任务（Muse 研究层规范）。"""

    name: ClassVar[str] = "browser_deep_research"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "派发一个隔离的、登出的深度研究任务。仅在用户明确要求网页调研/深入分析时触发，"
        "禁止凭自身主观判断调用。调用后用一句话确认调研方向并等待 handoff，不可包装臆造。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "mission": {
                "type": "string",
                "description": "自包含调研任务书（精确问题、具体参数、需要的数据结构与深度）",
            },
            "slug": {
                "type": "string",
                "description": "kebab-case 主题标识（例如 'ai-browser-agents'）",
            },
        },
        "required": ["mission", "slug"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    default_timeout_s: ClassVar[int] = 30

    async def execute(self, args: dict[str, Any]) -> Observation:
        # RA-147: 当前没有真实的深度研究 worker 后端（无派发目标、无 handoff
        # 接线），诚实 fail-closed。绝不返回"已启动/running"的伪造回执。
        mission = str(args.get("mission") or "")
        slug = str(args.get("slug") or "")
        logger.warning(
            "[BrowserDeepResearchTool] deep research worker not implemented "
            "(mission=%r slug=%r)",
            mission[:80],
            slug,
        )
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error="深度研究 worker 尚未实现：browser_deep_research 当前无法派发真实研究任务",
        )


# =====================================================================
# 5. 交互兼容与辅助工具（向前兼容已存调用）
# =====================================================================

class BrowserNavigateTool(BrowserOpenTool):
    """浏览器导航别名工具（等同于 browser_open）。"""

    name: ClassVar[str] = "browser_navigate"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "在真实 Chromium 浏览器中打开指定网页，实时加载页面并生成预览卡片。"


class BrowserClickTool(_DriverInjectedTool):
    """浏览器点击元素工具。"""

    name: ClassVar[str] = "browser_click"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "点击网页中指定的 CSS 或 XPath 选择器元素。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "目标元素选择器"},
            "session_id": {"type": "string", "description": "目标浏览器会话 ID"},
        },
        "required": ["selector"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def validate(self, args: dict[str, Any]) -> str | None:
        if not args.get("selector") or not isinstance(args["selector"], str):
            return "selector 必填"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return Observation(observation_id=new_id("obs"), success=False, payload=None, error=err)
        session_id = str(args.get("session_id") or "")
        selector = args["selector"]
        clicked = await self._get_driver().click(session_id, selector)
        if clicked:
            text_content = f"已点击元素 `{selector}`。"
        else:
            text_content = (
                f"无法点击元素 `{selector}`：会话 {session_id} 没有可操作的活动浏览器页面。"
            )
        res = BrowserActionResult(
            action_type=BrowserActionType.CLICK,
            success=clicked,
            session_id=session_id or None,
            text_content=text_content,
            details={"selector": selector, "live": clicked},
        )
        return Observation(observation_id=new_id("obs"), success=clicked, payload=res.model_dump())


class BrowserScreenshotTool(_DriverInjectedTool):
    """浏览器截屏工具。"""

    name: ClassVar[str] = "browser_screenshot"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "捕获当前网页可视区域或全页屏幕截图并生成 Artifact。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "目标浏览器会话 ID"},
        },
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    async def execute(self, args: dict[str, Any]) -> Observation:
        session_id = str(args.get("session_id") or "")
        art_id = new_id("art_screenshot")
        shot = await self._get_driver().take_screenshot(session_id)
        if shot is None:
            text_content = f"无法截屏：会话 {session_id} 没有活动浏览器页面。"
            res = BrowserActionResult(
                action_type=BrowserActionType.SCREENSHOT,
                success=False,
                session_id=session_id or None,
                screenshot_artifact_id=art_id,
                text_content=text_content,
                details={"live": False},
            )
            return Observation(
                observation_id=new_id("obs"), success=False, payload=res.model_dump()
            )
        text_content = (
            f"已捕获会话 {session_id} 的 JPEG 截图（{len(shot)} 字节），artifact_id={art_id}。"
        )
        res = BrowserActionResult(
            action_type=BrowserActionType.SCREENSHOT,
            success=True,
            session_id=session_id or None,
            screenshot_artifact_id=art_id,
            text_content=text_content,
            details={
                "live": True,
                "screenshot_bytes": len(shot),
                "screenshot_base64": base64.b64encode(shot).decode("ascii"),
            },
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


class BrowserCloseTool(_DriverInjectedTool):
    """浏览器会话关闭工具。"""

    name: ClassVar[str] = "browser_close"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "关闭指定的浏览器会话，释放 Chromium 页面与资源。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "要关闭的浏览器会话 ID"},
        },
        "required": ["session_id"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 10

    def validate(self, args: dict[str, Any]) -> str | None:
        if not args.get("session_id") or not isinstance(args["session_id"], str):
            return "session_id 必填"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return Observation(observation_id=new_id("obs"), success=False, payload=None, error=err)
        session_id = str(args["session_id"])
        driver = self._get_driver()
        closed = await driver.close_session(session_id)
        res = BrowserActionResult(
            action_type=BrowserActionType.CLOSE,
            success=closed,
            session_id=session_id,
            text_content=f"Session {session_id} closed={closed}",
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


class BrowserTypeTool(_DriverInjectedTool):
    """浏览器文本输入工具（兼容层：subagent TYPE 动作的共享执行支撑，RA-154）。"""

    name: ClassVar[str] = "browser_type"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "在网页指定的 CSS 或 XPath 选择器元素中输入文本。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "目标输入元素选择器"},
            "text": {"type": "string", "description": "要输入的文本内容"},
            "session_id": {"type": "string", "description": "目标浏览器会话 ID"},
        },
        "required": ["selector"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def validate(self, args: dict[str, Any]) -> str | None:
        if not args.get("selector") or not isinstance(args["selector"], str):
            return "selector 必填"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return Observation(observation_id=new_id("obs"), success=False, payload=None, error=err)
        session_id = str(args.get("session_id") or "")
        selector = args["selector"]
        text = str(args.get("text") or "")
        typed = False
        try:
            typed = await self._get_driver().type_text(session_id, selector, text)
        except Exception as exc:
            logger.warning("[BrowserTypeTool] live type failed: %s", exc)
        if typed:
            text_content = f"已在元素 `{selector}` 输入文本。"
        else:
            text_content = (
                f"无法输入文本：会话 {session_id} 没有可操作的活动浏览器页面。"
            )
        res = BrowserActionResult(
            action_type=BrowserActionType.TYPE,
            success=typed,
            session_id=session_id or None,
            text_content=text_content,
            details={"live": typed},
        )
        return Observation(observation_id=new_id("obs"), success=typed, payload=res.model_dump())


class BrowserExtractTextTool(_DriverInjectedTool):
    """浏览器页面文本提取工具（兼容层：subagent EXTRACT_TEXT 动作的共享执行支撑，RA-154）。"""

    name: ClassVar[str] = "browser_extract_text"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "提取当前浏览器页面可见文本内容。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "目标浏览器会话 ID"},
        },
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    async def execute(self, args: dict[str, Any]) -> Observation:
        session_id = str(args.get("session_id") or "")
        text = ""
        try:
            text = await self._get_driver().extract_text(session_id)
        except Exception as exc:
            logger.warning("[BrowserExtractTextTool] live extract failed: %s", exc)
        res = BrowserActionResult(
            action_type=BrowserActionType.EXTRACT_TEXT,
            success=True,
            session_id=session_id or None,
            text_content=text or "",
            details={"live": bool(text)},
        )
        return Observation(observation_id=new_id("obs"), success=True, payload=res.model_dump())


# =====================================================================
# 构建器导出
# =====================================================================

def build_browser_tools(driver: PlaywrightCDPDriver | None = None) -> list[Tool]:
    """构建 Muse 13 大工具 + 兼容扩展集合。"""
    arbitration = getattr(driver, "arbitration_engine", None) if driver is not None else None
    return [
        # 1. 轻量层 (4)
        BrowserSearchTool(),
        BrowserOpenTool(driver),
        BrowserFindTool(),
        BrowserLookupCitationUrlTool(),
        # 2. 实时任务层 (6)
        BrowserSpawnTaskTool(driver),
        BrowserSteerTaskTool(),
        BrowserListTasksTool(),
        BrowserPeekTaskTool(),
        BrowserCloseTaskTool(),
        BrowserTransferTaskTool(arbitration_engine=arbitration),
        # 3. CAPTCHA 偏好 (2)
        BrowserSetCaptchaPreferenceTool(),
        BrowserGetCaptchaPreferenceTool(),
        # 4. 研究层 (1)
        BrowserDeepResearchTool(),
        # 5. 兼容层
        BrowserNavigateTool(driver),
        BrowserClickTool(driver),
        BrowserScreenshotTool(driver),
        BrowserCloseTool(driver),
        BrowserTypeTool(driver),
        BrowserExtractTextTool(driver),
    ]


__all__ = [
    "BrowserClickTool",
    "BrowserCloseTaskTool",
    "BrowserCloseTool",
    "BrowserDeepResearchTool",
    "BrowserExtractTextTool",
    "BrowserFindTool",
    "BrowserGetCaptchaPreferenceTool",
    "BrowserListTasksTool",
    "BrowserLookupCitationUrlTool",
    "BrowserNavigateTool",
    "BrowserOpenTool",
    "BrowserPeekTaskTool",
    "BrowserScreenshotTool",
    "BrowserSearchTool",
    "BrowserSetCaptchaPreferenceTool",
    "BrowserSpawnTaskTool",
    "BrowserSteerTaskTool",
    "BrowserTransferTaskTool",
    "BrowserTypeTool",
    "build_browser_tools",
]
