"""Tests for the model-visible prompt catalog seam."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.protocols.memory.operational_skills import SkillIndexEntry
from lca.plugins.composer.prompt_catalog import ModelPromptCatalog


@dataclass(frozen=True)
class _Tool:
    name: str
    description: str | None = None


class _CountingSkillStore:
    def __init__(self, entries: tuple[SkillIndexEntry, ...]) -> None:
        self._entries = entries
        self.calls = 0

    def list_installed(self) -> tuple[SkillIndexEntry, ...]:
        self.calls += 1
        return self._entries


class _FailingSkillStore:
    def list_installed(self) -> tuple[SkillIndexEntry, ...]:
        raise OSError("skill index unavailable")


def test_catalog_reads_skill_store_once_and_reuses_immutable_index() -> None:
    store = _CountingSkillStore(
        (
            SkillIndexEntry(
                skill_id="code-review",
                name="Code Review",
                summary="Review a change for regressions.",
                version="2.0",
            ),
        )
    )

    catalog = ModelPromptCatalog.load(store, tools=(_Tool("read_file", "Read a file"),))

    assert store.calls == 1
    assert catalog.render_skill_discovery() == (
        "- code-review: Code Review — Review a change for regressions. (v2.0)"
    )
    assert catalog.render_brain_skills() == "- code-review: Code Review"
    assert catalog.render_tools_xml() == '<tool name="read_file">Read a file</tool>'
    assert store.calls == 1


def test_catalog_uses_stable_empty_renderings() -> None:
    catalog = ModelPromptCatalog.load(_CountingSkillStore(()))

    assert catalog.render_skill_discovery() == "（无可用技能；可使用 search_skill 查找）"
    assert catalog.render_brain_skills() == "（无可用技能）"
    assert catalog.render_tools_xml() == "（无可用工具）"


def test_catalog_does_not_hide_skill_store_failure() -> None:
    with pytest.raises(OSError, match="skill index unavailable"):
        ModelPromptCatalog.load(_FailingSkillStore())
