"""Tests for the Brain factory seam used by plan-bound Agent composition."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from lca.contracts.capabilities import BRAIN_PROMPT_CATALOG_FACTORY, BRAINS
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols.journal.spec import AgentSpec
from lca.plugins.composer.think import brain
from lca.plugins.composer.composition.prompt_catalog import DefaultBrainPromptCatalogFactory


class _BrainRegistry:
    """Minimal registry double returning a deliberately malformed factory result."""

    def resolve(self, _name: str) -> Callable[..., object]:
        return lambda *_args, **_kwargs: object()

    def names(self) -> tuple[str, ...]:
        return ("malformed",)


def test_resolve_brain_rejects_factory_output_outside_brain_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured provider must fail at composition rather than during a Turn."""

    spec = AgentSpec(
        profile=RoleProfile(
            role="tester",
            goal="verify factory contract",
            backstory="isolated composition test",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        ),
        llm=MagicMock(),
        brain="malformed",
    )
    monkeypatch.setattr(
        brain,
        "require_capability",
        lambda _scope, key: (
            _BrainRegistry()
            if key == BRAINS.key
            else DefaultBrainPromptCatalogFactory()
            if key == BRAIN_PROMPT_CATALOG_FACTORY.key
            else MagicMock()
        ),
    )
    monkeypatch.setattr(brain, "active_skill_store", lambda _scope: MagicMock())

    with pytest.raises(
        TypeError,
        match=r"brain factory 'malformed' produced object, expected Brain",
    ):
        brain.resolve_brain(spec, MagicMock(), scope=object())
