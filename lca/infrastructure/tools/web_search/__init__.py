"""web_search tool module — manifest + executor (lobe-web-browsing alignment)."""

from __future__ import annotations

import time
from typing import Any

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.infrastructure.capability.search import SearchService
from lca.infrastructure.search.service import (
    build_search_plugin_state,
    format_search_content,
    web_search,
)
from lca.infrastructure.tools.builder import build_tools_from_manifest

IDENTIFIER = "lobe-web-browsing"

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="search",
            description=(
                "联网搜索实时信息（新闻、最新动态、事实核查）。"
                "优先于 skill CLI 或沙箱 curl；参数 query 为搜索词。"
                "可选 topic=news|general|finance，time_range=day|week|month|year。"
            ),
            parameters={
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
            },
            is_idempotent=True,
        ),
    ),
    meta=ToolMeta(
        avatar="🔍", title="Web Search", description="Search the web for real-time information"
    ),
)


class WebSearchExecutor:
    """search seam Consumer — 只通过 SearchService（Definition）发请求。"""

    def __init__(self, search: SearchService | None = None) -> None:
        self._search = search

    async def search(self, params: dict[str, Any]) -> Observation:
        start = time.monotonic()
        query = str(params.get("query") or "").strip()
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

        topic = params.get("topic")
        time_range = params.get("time_range")
        topic_s = str(topic) if isinstance(topic, str) and topic.strip() else None
        range_s = str(time_range) if isinstance(time_range, str) and time_range.strip() else None

        if self._search is not None:
            result = await self._search.web_search(query, topic=topic_s, time_range=range_s)
        else:
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


def build_tools(search: SearchService | None = None) -> list[Tool]:
    return build_tools_from_manifest(MANIFEST, WebSearchExecutor(search))
