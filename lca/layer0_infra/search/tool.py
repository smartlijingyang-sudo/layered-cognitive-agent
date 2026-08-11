"""web_search tool — LobeHub lobe-web-browsing____search parity."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import Tool
from lca.layer0_infra.search.constants import WEB_SEARCH_TOOL
from lca.layer0_infra.search.service import (
    build_search_plugin_state,
    format_search_content,
    web_search,
)


class WebSearchTool(Tool):
    name = WEB_SEARCH_TOOL
    description = (
        "联网搜索实时信息（新闻、最新动态、事实核查）。"
        "优先于 skill CLI 或沙箱 curl；参数 query 为搜索词。"
        "可选 topic=news|general|finance，time_range=day|week|month|year。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询（建议 <400 字符）"},
            "topic": {
                "type": "string",
                "enum": ["general", "news", "finance"],
                "description": "搜索主题，新闻类用 news",
            },
            "time_range": {
                "type": "string",
                "enum": ["day", "week", "month", "year"],
                "description": "时间范围，今日新闻用 day",
            },
        },
        "required": ["query"],
    }
    is_idempotent = True
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        query = str(args.get("query") or "").strip()
        if not query:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error="query is required",
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )

        topic = args.get("topic")
        time_range = args.get("time_range")
        topic_s = str(topic) if isinstance(topic, str) and topic.strip() else None
        range_s = str(time_range) if isinstance(time_range, str) and time_range.strip() else None

        result = await web_search(query, topic=topic_s, time_range=range_s)
        latency_ms = int((time.monotonic() - start) * 1000)
        content = format_search_content(result)
        state = build_search_plugin_state(result)

        if result.ok:
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload={
                    "text": content,
                    "query": query,
                    "provider": result.provider,
                    "state": state,
                },
                latency_ms=latency_ms,
            )

        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload={"text": content, "query": query, "state": state},
            error=result.error or "search failed",
            latency_ms=latency_ms,
        )
