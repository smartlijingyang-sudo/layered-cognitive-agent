"""Unified search plane tests."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from lca.layer0_infra.search.models import SearchHit, SearchResponse
from lca.layer0_infra.search.router import is_search_intent, resolve_llm_search_kwargs
from lca.layer0_infra.search.scope import search_run_scope
from lca.layer0_infra.search.service import format_search_content
from lca.layer0_infra.tools.web_search import build_tools as build_web_search_tools


class TestSearchIntent(unittest.TestCase):
    def test_news_query_detected(self) -> None:
        self.assertTrue(is_search_intent("今天有什么新闻"))

    def test_non_search_query(self) -> None:
        self.assertFalse(is_search_intent("写一个 Python 排序函数"))


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
            "lca.layer0_infra.tools.web_search.web_search",
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
            with patch("lca.layer0_infra.search.router.get_llm_settings") as mock_llm:
                mock_llm.return_value.enable_search = True
                mock_llm.return_value.forced_search = False
                kwargs = resolve_llm_search_kwargs(task="今天有什么新闻")
        self.assertTrue(kwargs.get("enable_search"))


if __name__ == "__main__":
    unittest.main()
