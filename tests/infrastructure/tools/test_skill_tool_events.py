"""Skill tool meta-event wiring tests."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from lca.contracts.protocols.memory.operational_skills import SkillPackage, SkillSearchResult


@pytest.fixture
def package() -> SkillPackage:
    return SkillPackage(
        skill_id="demo-skill",
        name="Demo",
        content="---\nname: demo\n---\n# Demo",
        summary="demo",
        version="1",
        content_hash="sha256:demo",
        resource_paths=(),
        source_url="",
    )


def test_import_skill_emits_meta_events(package: SkillPackage) -> None:
    from lca.infrastructure.tools.skills.importer.import_tool import SkillImportTool

    class _Importer:
        async def import_from_market(self, ident: str) -> SkillPackage:
            return package

    tool = SkillImportTool(_Importer())
    with patch(
        "lca.infrastructure.observability.meta_event_emit.emit_skill_loaded",
    ) as loaded:
        obs = asyncio.run(tool.execute({"identifier": "demo-skill"}))
    assert obs.success is True
    loaded.assert_called_once()
    assert loaded.call_args.kwargs["skill_id"] == "demo-skill"


def test_activate_skill_emits_meta_events(package: SkillPackage) -> None:
    from lca.infrastructure.tools.skills.activate.tool import SkillActivateTool

    class _Store:
        def get(self, skill_id: str) -> SkillPackage:
            return package

        def list_installed(self) -> tuple:
            return ()

    tool = SkillActivateTool(_Store())
    with patch(
        "lca.infrastructure.observability.meta_event_emit.emit_skill_activated",
    ) as activated:
        obs = asyncio.run(tool.execute({"skill_id": "demo-skill"}))
    assert obs.success is True
    activated.assert_called_once()
    assert activated.call_args.kwargs["source"] == "tool:activate_skill"


def test_search_skill_emits_meta_events() -> None:
    from lca.infrastructure.tools.skills.search.tool import SkillSearchTool

    class _Importer:
        async def search_market(self, query: str, *, page: int, page_size: int) -> SkillSearchResult:
            return SkillSearchResult(items=(), total=0, page=page, page_size=page_size)

    class _Store:
        def list_installed(self) -> tuple:
            return ()

    tool = SkillSearchTool(_Importer(), _Store())
    with patch(
        "lca.infrastructure.observability.meta_event_emit.emit_skill_searched",
    ) as searched:
        obs = asyncio.run(tool.execute({"query": "pdf"}))
    assert obs.success is True
    searched.assert_called_once()
    assert searched.call_args.kwargs["query"] == "pdf"
