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
from typing import ClassVar, cast

import pytest

from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.contracts.protocols.assistant.role_resolver import RoleCard
from lca.plugins.assistant.persona.persona import persona_from_home
from lca.plugins.collaboration.modes.solo import build_solo_agent
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl
from lca.plugins.prompts.sections import (
    BackstorySection,
    CurrentDateSection,
    GoalSection,
    RoleSection,
)
from tests.harness.collector import InMemoryObservability
from tests.harness.scripted_llm import ScriptedLLMAdapter


class _StubRoleResolver:
    _CARDS: ClassVar[dict[str, RoleCard]] = {
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
        handle = catalog.create(CreateAssistantRequest(name="通用", description="通用助理"))
        spec = catalog.get(handle.assistant_id)
        role_profile = spec.agent_spec.profile

        output = BackstorySection().render(role_profile=role_profile, tools=[])
        assert "BACKSTORY:" in output.text
        assert len(output.text) > len("BACKSTORY: ")


class TestPersonaReachesSoloAgent:
    """ADR-0242 D3 集成：catalog → persona_from_home → build_solo_agent 非空。"""

    def test_role_profile_from_home_yields_non_empty_backstory(
        self, catalog: AssistantCatalogImpl
    ) -> None:
        handle = catalog.create(
            CreateAssistantRequest(
                name="小架",
                description="架构顾问",
                from_role="engineering/architect",
            )
        )
        spec = catalog.get(handle.assistant_id)
        persona = persona_from_home(spec.home_path)
        assert persona.role == "小架"
        assert persona.goal == "架构顾问"
        assert "系统架构专家" in persona.backstory

        role_profile = RoleProfile(
            role=persona.role,
            goal=persona.goal,
            backstory=persona.backstory,
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
        )
        llm = ScriptedLLMAdapter({}, default_respond=True)
        agent = build_solo_agent(
            llm,
            observability=InMemoryObservability(),
            role_profile=role_profile,
        )
        assert agent.role_profile.role == "小架"
        assert agent.role_profile.goal == "架构顾问"
        assert "系统架构专家" in agent.role_profile.backstory


class TestCurrentDateSectionLocale:
    """ADR-0242 D9/PR-8：CurrentDateSection 按 manifest.extra['locale'] 渲染星期。"""

    def _render(self, *, locale: str = "") -> SectionOutput:
        items = (
            ContextItem(
                kind="clock",
                payload="2026-09-18 Friday",
                provenance="clock_sensor",
            ),
        )
        extra = {"locale": locale} if locale else {}
        manifest = ContextManifest(items=items, extra=extra)
        return CurrentDateSection().render(
            role_profile=cast("RoleProfile", object()),
            task="",
            awareness=None,
            manifest=manifest,
            tools=[],
            activated_skills=(),
        )

    def test_zh_cn_localizes_weekday(self) -> None:
        output = self._render(locale="zh-CN")
        assert "CURRENT_DATE: 2026-09-18 星期五" in output.text

    def test_no_locale_keeps_english_weekday(self) -> None:
        output = self._render()
        assert "CURRENT_DATE: 2026-09-18 Friday" in output.text

    def test_unknown_locale_falls_back_to_english(self) -> None:
        output = self._render(locale="fr-FR")
        assert "CURRENT_DATE: 2026-09-18 Friday" in output.text
