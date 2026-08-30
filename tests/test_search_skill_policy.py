"""Unified search plane vs redundant Tavily CLI skills (ADR-0053)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from lca.contracts.protocols.operational_skills import SkillIndexEntry, SkillSearchResult
from lca.infrastructure.search.skill_policy import (
    filter_skill_search_result,
    is_redundant_cli_search_skill,
)
from lca.infrastructure.skills.disk_store import DiskSkillPackageStore
from lca.infrastructure.skills.http_importer import HttpSkillImporter
from lca.infrastructure.skills.settings import SkillSettings
from lca.infrastructure.tools.skills.activate_tool import SkillActivateTool
from lca.infrastructure.tools.skills.search_tool import SkillSearchTool


class TestSearchSkillPolicy(unittest.TestCase):
    def test_tavily_market_skill_is_redundant(self) -> None:
        self.assertTrue(
            is_redundant_cli_search_skill(
                skill_id="tavily-ai-skills-tavily-search",
                name="tavily-search",
            )
        )

    def test_xlsx_skill_is_not_redundant(self) -> None:
        self.assertFalse(
            is_redundant_cli_search_skill(
                skill_id="anthropics-skills-xlsx",
                name="xlsx",
            )
        )

    def test_filter_drops_tavily_when_unified_search_ready(self) -> None:
        result = SkillSearchResult(
            items=(
                SkillIndexEntry(
                    skill_id="tavily-ai-skills-tavily-search",
                    name="tavily-search",
                    summary="cli",
                ),
                SkillIndexEntry(
                    skill_id="anthropics-skills-xlsx",
                    name="xlsx",
                    summary="excel",
                ),
            ),
            total=2,
            page=1,
            page_size=20,
        )
        filtered = filter_skill_search_result(result, unified_search_available=True)
        self.assertEqual(len(filtered.items), 1)
        self.assertEqual(filtered.items[0].skill_id, "anthropics-skills-xlsx")

    def test_filter_keeps_all_when_unified_search_unavailable(self) -> None:
        result = SkillSearchResult(
            items=(
                SkillIndexEntry(
                    skill_id="tavily-ai-skills-tavily-search",
                    name="tavily-search",
                    summary="cli",
                ),
            ),
            total=1,
            page=1,
            page_size=20,
        )
        filtered = filter_skill_search_result(result, unified_search_available=False)
        self.assertEqual(filtered.items, result.items)


class TestSearchSkillToolFiltering(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        settings = SkillSettings(cache_dir=Path(self._tmp.name))
        self.store = DiskSkillPackageStore(settings)
        self.importer = HttpSkillImporter(store=self.store, settings=settings)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_search_skill_hides_tavily_when_api_configured(self) -> None:
        tool = SkillSearchTool(self.importer, self.store)
        market_result = SkillSearchResult(
            items=(
                SkillIndexEntry(
                    skill_id="tavily-ai-skills-tavily-search",
                    name="tavily-search",
                    summary="cli",
                ),
                SkillIndexEntry(
                    skill_id="anthropics-skills-pdf",
                    name="pdf",
                    summary="pdf",
                ),
            ),
            total=2,
            page=1,
            page_size=20,
        )
        with (
            patch.object(
                self.importer,
                "search_market",
                AsyncMock(return_value=market_result),
            ),
            patch(
                "lca.infrastructure.tools.skills.search_tool.any_search_provider_available",
                return_value=True,
            ),
        ):
            obs = await tool.execute({"query": "news search"})
        self.assertTrue(obs.success)
        text = obs.payload["text"]
        self.assertIn("anthropics-skills-pdf", text)
        self.assertNotIn("tavily-ai-skills-tavily-search", text)


class TestActivateSkillBlocksTavilyCli(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        settings = SkillSettings(cache_dir=Path(self._tmp.name))
        self.store = DiskSkillPackageStore(settings)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_activate_tavily_skill_rejected_when_web_search_ready(self) -> None:
        self.store.install_package(
            skill_id="tavily-ai-skills-tavily-search",
            skill_md_text="---\nname: tavily-search\n---\nUse tvly CLI",
            resource_files={},
            source_url="u",
        )
        tool = SkillActivateTool(self.store)
        with patch(
            "lca.infrastructure.tools.skills.activate_tool.any_search_provider_available",
            return_value=True,
        ):
            obs = await tool.execute({"skill_id": "tavily-ai-skills-tavily-search"})
        self.assertFalse(obs.success)
        self.assertIn("web_search", obs.error or "")


if __name__ == "__main__":
    unittest.main()
