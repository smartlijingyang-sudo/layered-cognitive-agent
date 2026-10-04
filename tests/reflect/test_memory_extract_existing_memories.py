"""``_format_existing_memories`` must show the extractor every live record.

``run_4fcfb6d83c8c`` stored 用户当前正在学习英语 twice, 15 seconds apart. One row
came from the ``memory_add`` tool and one from ``phase.reflect.memory.extract``.
The extractor's prompt tells it to reuse an existing ``dedupe_key`` when
revising a fact, but this helper filtered the candidate list to IDENTITY and
PREFERENCE, so the FACT already on disk was rendered as （无） and the extractor
minted ``fact:learning_language`` for a fact that was already stored.
``AssistantMemory._append_semantic`` converges on a shared ``dedupe_key`` or a
shared content fingerprint, and neither matched, so both rows stayed live.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.nodes.reflect.memory_extract.memory_extract import _format_existing_memories


@dataclass
class _Record:
    content: str
    category: MemoryCategory
    dedupe_key: str | None = None
    deleted: bool = False


class _Memory:
    def __init__(self, records: list[_Record]) -> None:
        self._records = records
        self.queried: list[Any] = []

    def query(self, layer: Any) -> list[_Record]:
        self.queried.append(layer)
        return list(self._records)


class _Runtime:
    def __init__(self, memory: _Memory) -> None:
        self.memory = memory


def test_fact_records_are_shown_to_the_extractor() -> None:
    memory = _Memory(
        [
            _Record(
                content="用户当前正在学习英语（2026年10月起）",
                category=MemoryCategory.FACT,
            ),
        ]
    )

    rendered = _format_existing_memories(_Runtime(memory))

    assert "用户当前正在学习英语（2026年10月起）" in rendered
    assert rendered != "（无）"
    assert memory.queried == [MemoryLayer.SEMANTIC]


def test_identity_and_preference_records_still_render() -> None:
    memory = _Memory(
        [
            _Record(
                content="称呼用户为老板",
                category=MemoryCategory.PREFERENCE,
                dedupe_key="pref:address",
            ),
            _Record(content="用户是架构师", category=MemoryCategory.IDENTITY),
        ]
    )

    rendered = _format_existing_memories(_Runtime(memory))

    assert "称呼用户为老板" in rendered
    assert "[dedupe_key: pref:address]" in rendered
    assert "用户是架构师" in rendered


def test_all_categories_render_together() -> None:
    """Every live category reaches the prompt, so a repeat is visible as a repeat."""
    memory = _Memory(
        [
            _Record(content="用户是架构师", category=MemoryCategory.IDENTITY),
            _Record(content="称呼用户为老板", category=MemoryCategory.PREFERENCE),
            _Record(content="用户当前正在学习英语", category=MemoryCategory.FACT),
        ]
    )

    rendered = _format_existing_memories(_Runtime(memory))

    for content in ("用户是架构师", "称呼用户为老板", "用户当前正在学习英语"):
        assert content in rendered
    assert len(rendered.splitlines()) == 3


def test_deleted_records_are_hidden() -> None:
    memory = _Memory(
        [
            _Record(content="用户住在上海", category=MemoryCategory.FACT, deleted=True),
            _Record(content="用户住在杭州", category=MemoryCategory.FACT),
        ]
    )

    rendered = _format_existing_memories(_Runtime(memory))

    assert "用户住在上海" not in rendered
    assert "用户住在杭州" in rendered


def test_empty_store_renders_the_placeholder() -> None:
    assert _format_existing_memories(_Runtime(_Memory([]))) == "（无）"


def test_missing_memory_renders_the_placeholder() -> None:
    """ADR-0246 §0.6 keeps extraction fail-soft, so an absent store degrades."""

    class _Bare:
        pass

    assert _format_existing_memories(_Bare()) == "（无）"
