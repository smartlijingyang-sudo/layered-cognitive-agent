"""SOUL.md → system prompt end-to-end verification.

Proves that when an assistant is created from a role card,
the SOUL.md content (role card backstory) appears in the
rendered system prompt via the BackstorySection.

Chain:
  RoleCard.backstory → catalog.create(from_role=...) → SOUL.md on disk
  → persona_from_home() → RoleProfile.backstory
  → BackstorySection.render() → "BACKSTORY: <soul>"
  → LLM system prompt
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.contracts.protocols.assistant.role_resolver import RoleCard
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl
from lca.plugins.prompts.sections import BackstorySection, RoleSection, GoalSection


class _StubRoleResolver:
    _CARDS = {
        "engineering/architect": RoleCard(
            role_id="engineering/architect",
            title="软件架构师",
            department="engineering",
            summary="系统设计专家",
            backstory=(
                "# 软件架构师\n\n"
                "你是系统架构专家，精通领域驱动设计和微服务架构。\n\n"
                "## 核心准则\n"
                "- 先理解现状再设计方案\n"
                "- 最小改动原则，不顺手重构\n"
                "- 所有决策需说明权衡"
            ),
            emoji="🏛️",
        ),
    }

    def resolve(self, role_id: str) -> RoleCard:
        if role_id not in self._CARDS:
            raise ValueError(f"unknown: {role_id}")
        return self._CARDS[role_id]

    def list_available(self) -> tuple[str, ...]:
        return tuple(sorted(self._CARDS))


@pytest.fixture
def catalog(tmp_path: Path) -> AssistantCatalogImpl:
    return AssistantCatalogImpl(
        root=tmp_path / "assistants",
        role_resolver=_StubRoleResolver(),
    )


class TestSoulReachesSystemPrompt:
    def test_backstory_section_contains_soul_content(self, catalog: AssistantCatalogImpl) -> None:
        """The BackstorySection must render SOUL.md content into the system prompt."""
        handle = catalog.create(
            CreateAssistantRequest(
                name="小架",
                description="架构顾问",
                from_role="engineering/architect",
            )
        )
        spec = catalog.get(handle.assistant_id)
        role_profile = spec.agent_spec.profile

        section = BackstorySection()
        output = section.render(role_profile=role_profile, tools=[])

        assert "系统架构专家" in output.text
        assert "领域驱动设计" in output.text
        assert "最小改动原则" in output.text
        assert output.text.startswith("BACKSTORY:")

    def test_role_section_contains_name(self, catalog: AssistantCatalogImpl) -> None:
        """The RoleSection must render the assistant name."""
        handle = catalog.create(
            CreateAssistantRequest(
                name="小架",
                description="架构顾问",
                from_role="engineering/architect",
            )
        )
        spec = catalog.get(handle.assistant_id)
        role_profile = spec.agent_spec.profile

        output = RoleSection().render(role_profile=role_profile, tools=[])
        assert "小架" in output.text

    def test_goal_section_contains_description(self, catalog: AssistantCatalogImpl) -> None:
        """The GoalSection must render the assistant description."""
        handle = catalog.create(
            CreateAssistantRequest(
                name="小架",
                description="架构顾问",
                from_role="engineering/architect",
            )
        )
        spec = catalog.get(handle.assistant_id)
        role_profile = spec.agent_spec.profile

        output = GoalSection().render(role_profile=role_profile, tools=[])
        assert "架构顾问" in output.text

    def test_soul_content_survives_round_trip(self, catalog: AssistantCatalogImpl) -> None:
        """SOUL.md on disk must match what the prompt section renders."""
        handle = catalog.create(
            CreateAssistantRequest(
                name="小架",
                description="架构顾问",
                from_role="engineering/architect",
            )
        )
        soul_on_disk = (Path(handle.home_path) / "SOUL.md").read_text(encoding="utf-8")
        spec = catalog.get(handle.assistant_id)
        role_profile = spec.agent_spec.profile

        output = BackstorySection().render(role_profile=role_profile, tools=[])
        for key_phrase in ("系统架构专家", "领域驱动设计", "最小改动原则"):
            assert key_phrase in soul_on_disk, f"{key_phrase} missing from SOUL.md on disk"
            assert key_phrase in output.text, f"{key_phrase} missing from BackstorySection output"

    def test_template_only_creation_also_has_soul(self, catalog: AssistantCatalogImpl) -> None:
        """Even without from_role, the template SOUL.md reaches the prompt."""
        handle = catalog.create(
            CreateAssistantRequest(name="通用", description="通用助理")
        )
        spec = catalog.get(handle.assistant_id)
        role_profile = spec.agent_spec.profile

        output = BackstorySection().render(role_profile=role_profile, tools=[])
        assert "BACKSTORY:" in output.text
        assert len(output.text) > len("BACKSTORY: ")
