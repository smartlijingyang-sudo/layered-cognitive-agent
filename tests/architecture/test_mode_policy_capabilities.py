"""Mode-policy capability gates for the remaining ADR-0076 substitution seams.

A run-mode adapter may assemble its local graph, but it must not become a second
source of truth for Creator persona, tool policy, Composer selection, or grants.
Likewise, the Team casting translator must only project tools materialized at the
profile boundary instead of restoring a concrete default tool set.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from lca.application.casting import build_from_casting_plan
from lca.cognition.team.modes.cordis_creator_mode import build_cordis_creator_agent
from lca.contracts.capabilities import CORDIS_CONTROL_TOOL_FACTORY, CORDIS_CREATOR_ROLE
from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest

REPO = Path(__file__).resolve().parents[2]


def _creator_role(*, allowed_tools: list[str]) -> RoleProfile:
    return RoleProfile(
        role="replacement-creator",
        goal="replaceable Creator goal",
        backstory="replaceable Creator backstory",
        tool_permission_manifest=ToolPermissionManifest(
            allowed_tools=allowed_tools,
            max_calls_per_task={},
            requires_approval=[],
        ),
    )


def test_creator_adapter_uses_profile_role_and_control_tool_factory(monkeypatch) -> None:
    """Changing role or control-tool providers changes Creator assembly only."""

    generic_tool = SimpleNamespace(name="replacement_generic", description="generic")
    control_tool = SimpleNamespace(name="cordis_control", description="control")

    class _ControlFactory:
        def __init__(self) -> None:
            self.calls: list[tuple[object | None, str]] = []

        def create(self, *, scope: object | None, actor_role: str) -> object:
            self.calls.append((scope, actor_role))
            return control_tool

    class _Scope:
        def __init__(self, factory: _ControlFactory) -> None:
            self._capabilities = {
                CORDIS_CREATOR_ROLE.key: _creator_role(
                    allowed_tools=["replacement_generic", "cordis_control"]
                ),
                CORDIS_CONTROL_TOOL_FACTORY.key: factory,
            }

        def inject(self, key: str) -> object:
            return self._capabilities[key]

    class _Agent:
        def __init__(self, *, role, goal, backstory, tools, llm, observability, scope) -> None:
            self.role_profile = SimpleNamespace(role=role, goal=goal, backstory=backstory)
            self.spec = SimpleNamespace(tools=tuple(tools))
            self.llm = llm
            self.observability = observability
            self.scope = scope

    monkeypatch.setattr("gateway.plugins.cordis_creator_mode.Agent", _Agent)
    factory = _ControlFactory()
    scope = _Scope(factory)
    agent = build_cordis_creator_agent(
        object(),  # The unit only verifies assembly data; the LLM is not invoked.
        observability=object(),
        scope=scope,
        tools=(generic_tool,),
    )

    assert agent.role_profile.role == "replacement-creator"
    assert agent.role_profile.goal == "replaceable Creator goal"
    assert [tool.name for tool in agent.spec.tools] == ["replacement_generic", "cordis_control"]
    assert factory.calls == [(scope, "replacement-creator")]


def test_creator_adapter_fails_closed_without_a_role_capability() -> None:
    """A Creator request cannot silently reconstruct the old built-in persona."""

    class _Scope:
        def inject(self, key: str) -> object:
            raise KeyError(key)

    with pytest.raises(MissingCapabilityError, match=CORDIS_CREATOR_ROLE.key):
        build_cordis_creator_agent(
            object(),
            observability=object(),
            scope=_Scope(),
            tools=(),
        )


def test_creator_adapter_has_no_local_persona_tools_or_grant_literals() -> None:
    """Static gate against reintroducing Creator policy into the Gateway adapter."""

    source = (REPO / "gateway" / "plugins" / "cordis_creator_mode.py").read_text(encoding="utf-8")
    assert "build_cordis_creator_role_profile" not in source
    assert "creator_names =" not in source
    assert "caller_grant=(" not in source
    assert "CORDIS_CREATOR_ROLE.key" in source
    assert "CORDIS_CONTROL_TOOL_FACTORY.key" in source


def test_casting_translation_requires_caller_materialized_tools() -> None:
    """The L4 translator cannot restore ``build_default_tools`` behind a fallback."""

    source = (REPO / "lca" / "application" / "casting.py").read_text(encoding="utf-8")
    tools_parameter = inspect.signature(build_from_casting_plan).parameters["tools"]

    assert "build_default_tools" not in source
    assert tools_parameter.default is inspect.Parameter.empty
