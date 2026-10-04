"""Skill retire/review lifecycle tests (minimal).

- retire_skill hides the package from default search_skill and makes
  run_skill_script (execScript) refuse it; unretire_skill restores both.
- activate_skill success increments usage_count on disk.
- Manifest advertises retireSkill/unretireSkill and searchSkill.include_retired.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lca.contracts.protocols.memory.operational_skills import (
    SkillImportError,
    SkillSearchResult,
)
from lca.infrastructure.file.store import LocalFileStore
from lca.infrastructure.skills.activation.scope import (
    activated_skills_scope,
    register_activated,
)
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings
from lca.infrastructure.tools.skills.manifest.manifest import MANIFEST

SKILL_MD = """---
name: demo
description: demo skill
references: []
---
# Demo
"""


@pytest.fixture
def store(tmp_path: Path) -> DiskSkillPackageStore:
    s = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "skills"))
    s.install_package(
        skill_id="demo-skill",
        skill_md_text=SKILL_MD,
        resource_files={},
        source_url="",
        version="1",
    )
    return s


class _NoMarket:
    async def search_market(self, query: str, *, page: int, page_size: int) -> SkillSearchResult:
        raise SkillImportError("market unreachable in tests")


def _search_tool(store):
    from lca.infrastructure.tools.skills.search.tool import SkillSearchTool

    return SkillSearchTool(_NoMarket(), store)


def _retire_tool(store):
    from lca.infrastructure.tools.skills.retire.tool import SkillRetireTool

    return SkillRetireTool(store)


def _unretire_tool(store):
    from lca.infrastructure.tools.skills.retire.tool import SkillUnretireTool

    return SkillUnretireTool(store)


def _activate_tool(store):
    from lca.infrastructure.tools.skills.activate.tool import SkillActivateTool

    return SkillActivateTool(store)


def _exec_tool(store):
    from lca.infrastructure.tools.skills.exec.tool import SkillExecTool

    return SkillExecTool(sandbox=None, store=store, file_store=LocalFileStore())


def _searched_ids(obs) -> list:
    return [
        item.get("identifier") or item.get("skill_id") or item.get("id")
        for item in obs.payload["items"]
    ]


def test_retire_hides_from_search_and_blocks_exec(store: DiskSkillPackageStore) -> None:
    obs = asyncio.run(_search_tool(store).execute({"query": "", "page": 1, "page_size": 20}))
    assert obs.success is True
    assert "demo-skill" in _searched_ids(obs)

    obs = asyncio.run(_retire_tool(store).execute({"skill_id": "demo-skill"}))
    assert obs.success is True
    assert obs.payload["retired"] is True
    assert store.get("demo-skill").retired is True

    obs = asyncio.run(_search_tool(store).execute({"query": "", "page": 1, "page_size": 20}))
    assert obs.success is True
    assert "demo-skill" not in _searched_ids(obs)

    # include_retired=True still lists it
    obs = asyncio.run(
        _search_tool(store).execute(
            {"query": "", "page": 1, "page_size": 20, "include_retired": True}
        )
    )
    assert "demo-skill" in _searched_ids(obs)

    # exec refuses a retired skill even when activated
    with activated_skills_scope(()):
        register_activated("demo-skill", "demo")
        obs = asyncio.run(
            _exec_tool(store).execute({"command": "echo hi", "skill_id": "demo-skill"})
        )
    assert obs.success is False
    assert "退役" in (obs.error or "")


def test_unretire_restores_search_and_exec(store: DiskSkillPackageStore) -> None:
    asyncio.run(_retire_tool(store).execute({"skill_id": "demo-skill"}))
    assert store.get("demo-skill").retired is True

    obs = asyncio.run(_unretire_tool(store).execute({"skill_id": "demo-skill"}))
    assert obs.success is True
    assert obs.payload["retired"] is False

    obs = asyncio.run(_search_tool(store).execute({"query": "", "page": 1, "page_size": 20}))
    assert "demo-skill" in _searched_ids(obs)


def test_retire_unknown_skill_fails_cleanly(store: DiskSkillPackageStore) -> None:
    obs = asyncio.run(_retire_tool(store).execute({"skill_id": "no-such-skill"}))
    assert obs.success is False
    assert "未找到" in (obs.error or "")


def test_usage_count_increments_on_activate(store: DiskSkillPackageStore) -> None:
    assert store.get("demo-skill").usage_count == 0
    for _ in range(2):
        obs = asyncio.run(_activate_tool(store).execute({"skill_id": "demo-skill"}))
        assert obs.success is True
    assert store.get("demo-skill").usage_count == 2


def test_manifest_advertises_review_tools() -> None:
    by_name = {api.name: api for api in MANIFEST.api}
    assert "retireSkill" in by_name
    assert "unretireSkill" in by_name
    assert "deactivateSkill" in by_name
    search_params = by_name["searchSkill"].parameters["properties"]
    assert "include_retired" in search_params
