"""PR-5（ADR-0246）：``USER_PROFILE`` prompt section 渲染测试。"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.plugins.prompts.sections import UserProfileSection


def _record(category: MemoryCategory, content: str) -> MemoryRecord:
    return MemoryRecord(
        record_id="mem_1",
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.8,
        category=category,
    )


def _manifest(records: list[MemoryRecord]) -> ContextManifest:
    return ContextManifest(
        items=(ContextItem(kind="memory", payload=records, provenance="memory.retrieve"),)
    )


def _render(section: UserProfileSection, manifest: ContextManifest | None) -> str:
    return section.render(
        role_profile=None,  # type: ignore[arg-type]
        task="",
        awareness=None,
        manifest=manifest,
        tools=(),
        activated_skills=(),
    ).text


def test_user_profile_renders_identity_and_preference() -> None:
    section = UserProfileSection()
    manifest = _manifest(
        [
            _record(MemoryCategory.IDENTITY, "用户身份：架构师"),
            _record(MemoryCategory.PREFERENCE, "用户偏好：不喜欢啰嗦"),
        ]
    )
    text = _render(section, manifest)
    assert text.startswith("USER_PROFILE:")
    assert "身份：用户身份：架构师" in text
    assert "偏好：用户偏好：不喜欢啰嗦" in text


def test_user_profile_empty_without_identity_or_preference() -> None:
    section = UserProfileSection()
    manifest = _manifest([_record(MemoryCategory.FACT, "一般事实")])
    assert _render(section, manifest) == ""


def test_user_profile_empty_with_null_manifest() -> None:
    section = UserProfileSection()
    assert _render(section, None) == ""
