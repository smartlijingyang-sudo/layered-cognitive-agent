"""web_search tool module — manifest + executor (lobe-web-browsing alignment)."""

from __future__ import annotations

import time
from typing import Any

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.infrastructure.capability.search.search import SearchService
from lca.infrastructure.search.service.service import (
    build_search_plugin_state,
    format_search_content,
    web_search,
)
from lca.infrastructure.tools.builder.builder import build_tools_from_manifest

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
            namespace="web",
        ),
    ),
    meta=ToolMeta(
        avatar="🔍", title="Web Search", description="Search the web for real-time information"
    ),
)


class WebSearchExecutor:
    """search seam Consumer — 双路径声明（叙事 == 实现，RA-148）：

    - ``search`` 给了 SearchService（kernel Definition seam，ctx.search 的拥有者）
      时走它：单活 provider 派发（ProviderDispatch.current()）。
    - ``search`` 为 None 时走 infrastructure 的 ambient ``web_search``
      （``lca/infrastructure/search/service/service.py``）：按
      ``configured_provider_ids()`` 有序 fallback，用于无 kernel 上下文的
      独立场景。

    实际走的 seam 写进 ``Observation.extra["search_seam"]``
    （``"definition"`` | ``"ambient"``）——接口层面可区分、可测试。
    """

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
            seam = "definition"
            result = await self._search.web_search(query, topic=topic_s, time_range=range_s)
        else:
            seam = "ambient"
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
                extra={"search_seam": seam},
            )

        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload={"text": content, "query": query, "state": state},
            error=result.error or "search failed",
            latency_ms=latency_ms,
            extra={"search_seam": seam},
        )


def build_tools(search: SearchService | None = None) -> list[Tool]:
    return build_tools_from_manifest(MANIFEST, WebSearchExecutor(search))
