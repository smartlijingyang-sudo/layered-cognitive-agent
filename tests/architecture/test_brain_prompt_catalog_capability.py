"""Substitution gates for the Brain-visible tools and skills catalog primitive."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import pytest

from lca.contracts.capabilities import BRAIN_PROMPT_CATALOG_FACTORY, BRAINS
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols.journal.spec import AgentSpec
from lca.harness.profile.resolve import resolve_profile
from lca.plugins.composer.internal import brain
from lca.plugins.composer.prompt_catalog import DefaultBrainPromptCatalogFactory

REPO = Path(__file__).resolve().parents[2]


class _SkillStore:
    """Minimal selected skill store for catalog factory verification."""

    def list_installed(self) -> tuple[object, ...]:
        return ()


class _Catalog:
    """Custom catalog proving the Brain composer consumes the selected primitive."""

    def render_tools_xml(self) -> str:
        return "<custom-tool-catalog />"

    def render_brain_skills(self) -> str:
        return "custom-skill-catalog"


class _CatalogFactory:
    """Record composition inputs and return a profile-selected catalog."""

    def __init__(self) -> None:
        self.skill_store: object | None = None
        self.tools: tuple[object, ...] = ()

    def create(self, *, skill_store: object, tools: object) -> _Catalog:
        self.skill_store = skill_store
        self.tools = tuple(tools)  # type: ignore[arg-type]
        return _Catalog()


class _Brain:
    """Minimal structural Brain implementation returned by the configured factory."""

    async def think(self, state: AgentState) -> Decision:
        del state
        raise AssertionError("this composition test must not execute the Brain")

    async def reflect(self, state: AgentState, observation: Observation) -> Reflection:
        del state, observation
        raise AssertionError("this composition test must not execute the Brain")


class _BrainRegistry:
    """Registry double that captures the exact prompt inputs passed to its factory."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def resolve(self, _name: str) -> Callable[..., _Brain]:
        def factory(*args: object, **kwargs: object) -> _Brain:
            self.calls.append((args, kwargs))
            return _Brain()

        return factory

    def names(self) -> tuple[str, ...]:
        return ("custom",)


def _spec() -> AgentSpec:
    return AgentSpec(
        profile=RoleProfile(
            role="tester",
            goal="verify profile-selected prompt catalog",
            backstory="isolated composition test",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        ),
        llm=MagicMock(),
        brain="custom",
    )


def test_default_factory_freezes_selected_skills_and_tools() -> None:
    """The default primitive preserves the established immutable catalog behavior."""

    catalog = DefaultBrainPromptCatalogFactory().create(skill_store=_SkillStore(), tools=())

    assert catalog.render_brain_skills() == "（无可用技能）"
    assert catalog.render_tools_xml() == "（无可用工具）"


def test_standard_profile_provides_brain_prompt_catalog_factory() -> None:
    """Production composition selects the primitive explicitly through the Web bundle."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    by_id = {plugin.id: plugin.definition for plugin in resolved.plugins}

    assert (
        BRAIN_PROMPT_CATALOG_FACTORY.key
        in by_id["lca-brain-prompt-catalog-default"].provided_capability_keys
    )


def test_resolve_brain_consumes_profile_selected_prompt_catalog_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replacing the catalog only changes its capability binding, not BrainComposer."""

    registry = _BrainRegistry()
    catalog_factory = _CatalogFactory()
    skill_store = _SkillStore()

    def require(scope: object, key: str) -> object:
        del scope
        if key == BRAINS.key:
            return registry
        if key == BRAIN_PROMPT_CATALOG_FACTORY.key:
            return catalog_factory
        raise AssertionError(f"unexpected capability: {key}")

    monkeypatch.setattr(brain, "require_capability", require)
    monkeypatch.setattr(brain, "active_skill_store", lambda _scope: skill_store)

    composed = brain.resolve_brain(_spec(), MagicMock(), scope=object())

    assert isinstance(composed, _Brain)
    assert catalog_factory.skill_store is skill_store
    assert catalog_factory.tools == ()
    assert len(registry.calls) == 1
    _args, kwargs = registry.calls[0]
    assert _args[2] == "<custom-tool-catalog />"
    assert kwargs["available_skills"] == "custom-skill-catalog"


def test_brain_composer_has_no_direct_prompt_catalog_implementation() -> None:
    """Only the selected primitive may choose the concrete prompt-catalog implementation."""

    source = (REPO / "lca/plugins/composer/internal/brain.py").read_text(encoding="utf-8")

    assert "ModelPromptCatalog" not in source
    assert BRAIN_PROMPT_CATALOG_FACTORY.key in source
