"""Unified search plane tests."""

from __future__ import annotations

import unittest
from datetime import UTC
from unittest.mock import AsyncMock, patch

from lca.infrastructure.search.models.models import SearchHit, SearchResponse
from lca.infrastructure.search.router.router import is_search_intent, resolve_llm_search_kwargs
from lca.infrastructure.search.scope.scope import search_run_scope
from lca.infrastructure.search.service.service import format_search_content
from lca.infrastructure.tools.web_search import build_tools as build_web_search_tools


class TestSearchIntent(unittest.TestCase):
    def test_news_query_detected(self) -> None:
        self.assertTrue(is_search_intent("今天有什么新闻"))

    def test_non_search_query(self) -> None:
        self.assertFalse(is_search_intent("写一个 Python 排序函数"))

    def test_freshness_and_version_queries_detected(self) -> None:
        self.assertTrue(is_search_intent("2026年最新进展"))
        self.assertTrue(is_search_intent("Python 3.13 changelog"))
        self.assertTrue(is_search_intent("Exa API latest release"))
        self.assertTrue(is_search_intent("查看这个库的更新说明"))
        self.assertFalse(is_search_intent("实现一个二叉树前序遍历算法"))

    def test_availability_price_freshness_detected(self) -> None:
        """D2-T7 contract: stock/price are time-varying facts parametric
        knowledge cannot answer; they must route to realtime search
        (ADR-0276 T7: tool routing verified on the real router)."""
        positives = [
            "查某商品现在有没有货",
            "这款耳机是否有货",
            "iPhone 17 还有库存吗",
            "帮我看下这款手机的现价",
            "这双鞋的最新价格是多少",
            "实时价格",
            "当前价格",
            "Is the Pixel in stock right now?",
            "What's the current price of the MacBook?",
        ]
        for query in positives:
            with self.subTest(query=query):
                self.assertTrue(is_search_intent(query))

    def test_deliberately_excluded_patterns_stay_off(self) -> None:
        """D2-T7 negative contract: 过宽的"现在"/"多少钱"被刻意排除（误路由只多一个
        search hint，漏路由才幻觉），不得单独触发路由。"""
        negatives = [
            "现在几点",
            "现在有空吗",
            "这个多少钱",
            "这双鞋现在多少钱",
        ]
        for query in negatives:
            with self.subTest(query=query):
                self.assertFalse(is_search_intent(query))

    def test_search_routing_hint_freshness(self) -> None:
        from datetime import datetime

        from lca.infrastructure.search.router.router import search_routing_hint

        hint = search_routing_hint(tavily_available=True)
        self.assertIn("Freshness-First", hint)
        self.assertIn("CURRENT_DATE", hint)
        current_year = str(datetime.now(UTC).year)
        self.assertIn(current_year, hint)

    def test_dynamic_temporal_year_boundary(self) -> None:
        from datetime import datetime

        curr = datetime.now(UTC).year
        # Current and near future years with freshness verbs match
        self.assertTrue(is_search_intent(f"{curr}年最新进展"))
        self.assertTrue(is_search_intent(f"{curr + 1} release status"))
        # Distant past years (before 2024) do not trigger freshness intent
        self.assertFalse(is_search_intent("2015年历史进展"))
        # Distant future years (> curr + 5) do not trigger freshness intent
        self.assertFalse(is_search_intent(f"{curr + 10}年进展"))


class TestSearchFormatting(unittest.TestCase):
    def test_format_hits(self) -> None:
        resp = SearchResponse(
            query="news",
            provider="tavily",
            results=(SearchHit(title="Headline", url="https://example.com", content="body"),),
            answer="summary",
        )
        text = format_search_content(resp)
        self.assertIn("Headline", text)
        self.assertIn("summary", text)


class TestWebSearchTool(unittest.IsolatedAsyncioTestCase):
    async def test_requires_query(self) -> None:
        tool = build_web_search_tools()[0]
        obs = await tool.execute({})
        self.assertFalse(obs.success)

    async def test_success_payload(self) -> None:
        tool = build_web_search_tools()[0]
        ok = SearchResponse(
            query="AI news",
            provider="tavily",
            results=(SearchHit(title="A", url="https://a.test", content="c"),),
            answer="ok",
        )
        with patch(
            "lca.infrastructure.tools.web_search.web_search",
            new=AsyncMock(return_value=ok),
        ):
            obs = await tool.execute({"query": "AI news", "topic": "news"})
        self.assertTrue(obs.success)
        assert obs.payload is not None
        self.assertIn("state", obs.payload)


class TestLlmFallbackRouting(unittest.TestCase):
    def test_prefers_llm_after_web_search_failure(self) -> None:
        with search_run_scope() as state:
            state.web_search_failed = True
            state.prefer_llm_search = True
            with patch("lca.infrastructure.search.router.router.get_llm_settings") as mock_llm:
                mock_llm.return_value.enable_search = True
                mock_llm.return_value.forced_search = False
                kwargs = resolve_llm_search_kwargs(task="今天有什么新闻")
        self.assertTrue(kwargs.get("enable_search"))


if __name__ == "__main__":
    unittest.main()
