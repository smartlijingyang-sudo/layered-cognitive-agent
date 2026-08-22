"""Tests for the strict plan-bound L4 composition path."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from lca.contracts.harness import AgentGraph, TeamGraph
from lca.contracts.harness.composer import (
    agent_graph_has_body,
    agent_graph_has_brain,
    merge_agent_graphs,
    team_graph_member_count,
)
from lca.layer4_app.spawn_bind_plan import (
    BindPlanError,
    PlanBindingResult,
    TeamBindingResult,
    bind_plan,
    bind_team,
)
from lca.plugins.composer.plan_composition_support import AgentCompositionRequest


class TestGraphContracts:
    def test_agent_graph_absence_is_visible(self) -> None:
        graph = AgentGraph(
            brain=None,
            body=None,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=None,
            stop_rule=None,
        )
        assert not agent_graph_has_brain(graph)
        assert not agent_graph_has_body(graph)
        assert graph.metadata == {}

    def test_team_graph_member_count(self) -> None:
        graph = TeamGraph(members=(), strategy=None, stage=None, transport=None, observability=None)
        assert team_graph_member_count(graph) == 0

    def test_merge_preserves_disjoint_contributions(self) -> None:
        brain_graph = AgentGraph(
            brain="brain",
            body=None,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=None,
            stop_rule=None,
        )
        body_graph = AgentGraph(
            brain=None,
            body="body",
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=None,
            stop_rule=None,
        )
        merged = merge_agent_graphs(brain_graph, body_graph)
        assert merged.brain == "brain"
        assert merged.body == "body"


class _StubScope:
    def __init__(self, capabilities: dict[str, object] | None = None) -> None:
        self._capabilities = capabilities or {}

    def inject(self, key: str) -> Any:
        if key not in self._capabilities:
            raise KeyError(f"missing: {key}")
        return self._capabilities[key]


class _Composer:
    def __init__(self, key: str) -> None:
        self.key = key

    def compose_agent(self, request: AgentCompositionRequest, scope: object) -> AgentGraph:
        del request, scope
        values: dict[str, Any] = {
            "brain": {"brain": "brain", "llm": "llm"},
            "body": {"body": "body", "hooks": "hooks"},
            "perceive": {
                "memory": "memory",
                "state_store": "state_store",
                "perceive_hub": "perceive_hub",
                "observability": "observability",
                "stop_rule": "stop_rule",
            },
        }[self.key]
        return AgentGraph(
            brain=values.get("brain"),
            body=values.get("body"),
            memory=values.get("memory"),
            state_store=values.get("state_store"),
            perceive_hub=values.get("perceive_hub"),
            hooks=values.get("hooks"),
            observability=values.get("observability"),
            llm=values.get("llm"),
            stop_rule=values.get("stop_rule"),
            metadata={"composer": self.key},
        )

    def compose_team(self, spec: object, scope: object) -> TeamGraph:
        del spec, scope
        if self.key != "team":
            raise TypeError("only team composes teams")
        return TeamGraph(
            members=("member",),
            strategy="strategy",
            stage="stage",
            transport="transport",
            observability="observability",
            metadata={"lead": None},
        )


def _full_scope() -> _StubScope:
    return _StubScope(
        {
            "composer.brain": _Composer("brain"),
            "composer.body": _Composer("body"),
            "composer.perceive": _Composer("perceive"),
            "composer.team": _Composer("team"),
        }
    )


class TestStrictPlanBinding:
    def test_missing_required_composer_fails(self) -> None:
        scope = _StubScope({"composer.brain": _Composer("brain")})
        with pytest.raises(BindPlanError, match=r"required composer\.body"):
            bind_plan(_request(), _plan(), scope=scope)

    def test_scope_without_inject_fails(self) -> None:
        with pytest.raises(BindPlanError, match="booted cordis Context"):
            bind_plan(_request(), _plan(), scope=object())

    def test_complete_composers_return_complete_plan_binding(self) -> None:
        result = bind_plan(_request(), _plan(), scope=_full_scope())
        assert isinstance(result, PlanBindingResult)
        assert result.graph.brain == "brain"
        assert result.graph.body == "body"
        assert result.metadata == {"composers": ("brain", "body", "perceive")}

    def test_plan_ref_is_propagated(self) -> None:
        from lca.contracts.protocols.plan import compiled_run_plan_ref

        plan = _plan()
        result = bind_plan(_request(), plan, scope=_full_scope())
        assert result.plan_ref == compiled_run_plan_ref(plan)

    def test_unresolvable_provider_binding_fails_closed(self) -> None:
        with pytest.raises(BindPlanError, match="missing_capability"):
            bind_plan(_request(), _plan(with_binding=True), scope=_full_scope())


class TestStrictTeamBinding:
    def test_missing_team_composer_fails(self) -> None:
        with pytest.raises(BindPlanError, match=r"required composer\.team"):
            bind_team(_team_spec(), _plan(), scope=_StubScope())

    def test_complete_team_composer_returns_binding(self) -> None:
        result = bind_team(_team_spec(), _plan(), scope=_full_scope())
        assert isinstance(result, TeamBindingResult)
        assert result.graph.members == ("member",)
        assert result.metadata == {"composer": "team"}


class TestDefaultProfilePlanBinding:
    @pytest.mark.asyncio
    async def test_default_profile_binds_plan_to_solo_agent(self) -> None:
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from lca.layer4_app.api import ensure_default_ctx
        from lca.layer4_app.spawn import spawn_agent
        from tests.support.agent_specs import make_spec

        scope = await ensure_default_ctx()
        agent = spawn_agent(make_spec("plan-bound", MockLLMAdapter()), scope=scope)
        assert agent.plan_ref
        assert agent.runtime is not None

    def test_spawn_agent_exposes_no_legacy_selection_parameters(self) -> None:
        from lca.layer4_app.spawn import spawn_agent

        parameters = inspect.signature(spawn_agent).parameters
        assert "compiled_plan" not in parameters
        assert "use_bind_plan" not in parameters


def _plan(*, with_binding: bool = False) -> Any:
    from lca.contracts.atoms.scope import Scope
    from lca.contracts.protocols.capability_plan import CapabilityPlan, ProviderBinding
    from lca.contracts.protocols.control_plan import ControlPlan
    from lca.contracts.protocols.plan import CompiledRunPlan
    from lca.contracts.protocols.scope_plan import BudgetCeiling, ScopePlan

    bindings = (
        (ProviderBinding(capability="missing_capability", owner_plugin="missing_plugin"),)
        if with_binding
        else ()
    )
    return CompiledRunPlan(
        profile_path="test.yaml",
        capability=CapabilityPlan(
            profile_path="test.yaml", provider_bindings=bindings, relations=()
        ),
        control=ControlPlan(profile_path="test.yaml", entries=(), by_slot={}, plan_hash="0" * 16),
        scope=ScopePlan(
            profile_path="test.yaml",
            lifecycle=Scope.RUN,
            visibility=(Scope.RUN,),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        ),
    )


def _request() -> AgentCompositionRequest:
    from unittest.mock import MagicMock

    return AgentCompositionRequest(spec=MagicMock())


def _team_spec() -> object:
    from unittest.mock import MagicMock

    return MagicMock()
