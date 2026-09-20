"""PR-5（ADR-0246）：CONTEXT 记忆行输出结构化事实。"""

from __future__ import annotations

from lca.cognition.brain.sections.types import format_record_line, render_context_lines
from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest


def _record(category: MemoryCategory, content: str) -> MemoryRecord:
    return MemoryRecord(
        record_id="mem_1",
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.8,
        category=category,
    )


def test_identity_record_line_is_structured() -> None:
    line = format_record_line(_record(MemoryCategory.IDENTITY, "用户身份：架构师"))
    assert line == "- [identity] 用户身份：架构师"
    assert "[semantic]" not in line


def test_preference_record_line_is_structured() -> None:
    line = format_record_line(_record(MemoryCategory.PREFERENCE, "用户偏好：不喜欢啰嗦"))
    assert line == "- [preference] 用户偏好：不喜欢啰嗦"


def test_fact_record_line_uses_category() -> None:
    line = format_record_line(_record(MemoryCategory.FACT, "一般事实"))
    assert line == "- [fact] 一般事实"


def test_context_renders_structured_memory_lines() -> None:
    manifest = ContextManifest(
        items=(
            ContextItem(
                kind="memory",
                payload=[_record(MemoryCategory.IDENTITY, "用户身份：架构师")],
                provenance="memory.retrieve",
            ),
        )
    )
    body = render_context_lines(manifest)
    assert "- [identity] 用户身份：架构师" in body
