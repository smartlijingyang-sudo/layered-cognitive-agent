"""Tests for the strict plan-bound L4 composition path."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from lca.contracts.harness import AgentGraphContribution, TeamGraph
from lca.contracts.harness.composer import (
    AgentCompositionRequest,
    merge_agent_graphs,
    team_graph_member_count,
)
from lca.plugins.composer.plan_binding import (
    BindPlanError,
    PlanBindingResult,
    TeamBindingResult,
    bind_agent_from_scope,
    bind_plan,
    bind_team,
    bind_team_from_scope,
)


class TestGraphContracts:
    def test_agent_graph_contribution_makes_absence_explicit(self) -> None:
        contribution = AgentGraphContribution()
        assert contribution.brain is None
        assert contribution.body is None
        assert contribution.metadata == {}

    def test_team_graph_member_count(self) -> None:
        graph = TeamGraph(members=(), strategy=None, stage=None, transport=None, observability=None)
        assert team_graph_member_count(graph) == 0

    def test_merge_rejects_an_incomplete_agent_graph(self) -> None:
        with pytest.raises(ValueError, match="AgentGraph is incomplete"):
            merge_agent_graphs(AgentGraphContribution(brain="brain"))

    def test_merge_closes_disjoint_contributions(self) -> None:
        brain_contribution = AgentGraphContribution(brain="brain", llm="llm")
        body_contribution = AgentGraphContribution(body="body", hooks="hooks")
        perceive_contribution = AgentGraphContribution(
            memory="memory",
            state_store="state_store",
            perceive_hub="perceive_hub",
            observability="observability",
            phase_capabilities={"stop_policy": "stop_policy"},
        )
        merged = merge_agent_graphs(brain_contribution, body_contribution, perceive_contribution)
        assert merged.brain == "brain"
        assert merged.body == "body"

    def test_merge_rejects_duplicate_field_contributions(self) -> None:
        """A plan must not let capability ordering choose a runtime dependency."""
        primary = AgentGraphContribution(brain="primary", metadata={"composer": "brain"})
        replacement = AgentGraphContribution(
            brain="replacement", metadata={"composer": "fallback-brain"}
        )

        with pytest.raises(
            ValueError,
            match="AgentGraph contribution conflict for 'brain': 'brain' and 'fallback-brain'",
        ):
            merge_agent_graphs(primary, replacement)


class _StubScope:
    def __init__(self, capabilities: dict[str, object] | None = None) -> None:
        self._capabilities = capabilities or {}

    def inject(self, key: str) -> Any:
        if key not in self._capabilities:
            raise KeyError(f"missing: {key}")
        return self._capabilities[key]


class _AgentComposer:
    def __init__(self, key: str) -> None:
        self.key = key

    def compose_agent(
        self, request: AgentCompositionRequest, scope: object
    ) -> AgentGraphContribution:
        del request, scope
        values: dict[str, Any] = {
            "brain": {"brain": "brain", "llm": "llm"},
            "body": {"body": "body", "hooks": "hooks"},
            "perceive": {
                "memory": "memory",
                "state_store": "state_store",
                "perceive_hub": "perceive_hub",
                "observability": "observability",
                "phase_capabilities": {"stop_policy": "stop_policy"},
            },
        }[self.key]
        return AgentGraphContribution(
            brain=values.get("brain"),
            body=values.get("body"),
            memory=values.get("memory"),
            state_store=values.get("state_store"),
            perceive_hub=values.get("perceive_hub"),
            hooks=values.get("hooks"),
            observability=values.get("observability"),
            llm=values.get("llm"),
            phase_capabilities=values.get("phase_capabilities", {}),
            metadata={"composer": self.key},
        )


class _TeamComposer:
    key = "team"

    def compose_team(self, spec: object, scope: object) -> TeamGraph:
        del spec, scope
        return TeamGraph(
            members=("member",),
            strategy="strategy",
            stage="stage",
            transport="transport",
            observability="observability",
            lead=None,
            metadata={"composer": self.key},
        )


def _full_scope() -> _StubScope:
    return _StubScope(
        {
            "composer.brain": _AgentComposer("brain"),
            "composer.body": _AgentComposer("body"),
            "composer.perceive": _AgentComposer("perceive"),
            "composer.team": _TeamComposer(),
        }
    )


class TestStrictPlanBinding:
    def test_partial_composers_fail_at_the_graph_closure_seam(self) -> None:
        """A plan with only a subset of Agent composers cannot produce a
        runnable AgentGraph.

        Individual composers may return partial contributions, but binding is
        the one closure seam and must reject missing runtime dependencies.
        """
        from lca.contracts.protocols.plan import CapabilityBinding

        plan = _plan(
            with_capability_bindings=(
                CapabilityBinding(
                    capability="composer.brain",
                    provider="plugin.composer.brain",
                    cardinality="one",
                ),
            ),
        )
        scope = _StubScope(
            {
                "composer.brain": _AgentComposer("brain"),
                "composer.body": _AgentComposer("body"),
                "composer.perceive": _AgentComposer("perceive"),
            }
        )
        with pytest.raises(BindPlanError, match="AgentGraph is incomplete"):
            bind_plan(_request(), plan, scope=scope)

    def test_scope_without_inject_fails(self) -> None:
        with pytest.raises(BindPlanError, match="booted cordis Context"):
            bind_plan(_request(), _plan(), scope=object())

    def test_complete_composers_return_complete_plan_binding(self) -> None:
        from lca.contracts.protocols.plan import CapabilityBinding

        plan = _plan(
            with_capability_bindings=tuple(
                CapabilityBinding(
                    capability=key,
                    provider=f"plugin.{key}",
                    cardinality="one",
                )
                for key in ("composer.brain", "composer.body", "composer.perceive")
            )
        )
        result = bind_plan(_request(), plan, scope=_full_scope())
        assert isinstance(result, PlanBindingResult)
        assert result.graph.brain == "brain"
        assert result.graph.body == "body"
        assert result.composer_capabilities == (
            "composer.body",
            "composer.brain",
            "composer.perceive",
        )

    def test_agent_binding_reads_the_plan_frozen_on_the_scope(self) -> None:
        """Production Agent binding must not accept a second plan interpretation."""

        from lca.contracts.protocols.plan import CapabilityBinding
        from lca.harness.profile.boot_products import (
            ProfileBootProducts,
            attach_profile_boot_products,
        )

        plan = _plan(
            with_capability_bindings=tuple(
                CapabilityBinding(
                    capability=key,
                    provider=f"plugin.{key}",
                    cardinality="one",
                )
                for key in ("composer.brain", "composer.body", "composer.perceive")
            )
        )
        scope = _full_scope()
        attach_profile_boot_products(scope, ProfileBootProducts(compiled_run_plan=plan))

        result = bind_agent_from_scope(_request().spec, scope=scope)

        assert result.plan is plan
        assert result.composer_capabilities == (
            "composer.body",
            "composer.brain",
            "composer.perceive",
        )

    def test_team_composer_is_not_called_while_binding_agent_graph(self) -> None:
        """A Team-only composer cannot join AgentGraph composition by accident."""

        from lca.contracts.protocols.plan import CapabilityBinding

        plan = _plan(
            with_capability_bindings=tuple(
                CapabilityBinding(
                    capability=key,
                    provider=f"plugin.{key}",
                    cardinality="one",
                )
                for key in ("composer.brain", "composer.body", "composer.perceive", "composer.team")
            )
        )
        result = bind_plan(_request(), plan, scope=_full_scope())
        assert result.composer_capabilities == (
            "composer.body",
            "composer.brain",
            "composer.perceive",
        )

    def test_plan_ref_is_propagated(self) -> None:
        from lca.contracts.protocols.declarative_phase_graph import CapabilityBinding
        from lca.harness.plan import compiled_run_plan_ref

        plan = _plan(
            with_capability_bindings=tuple(
                CapabilityBinding(
                    capability=key,
                    provider=f"plugin.{key}",
                    cardinality="one",
                )
                for key in ("composer.brain", "composer.body", "composer.perceive")
            )
        )
        result = bind_plan(_request(), plan, scope=_full_scope())
        assert result.plan_ref == compiled_run_plan_ref(plan)

    def test_unresolvable_provider_binding_fails_closed(self) -> None:
        from lca.contracts.protocols.plan import CapabilityBinding

        plan = _plan(
            with_binding=True,
            with_capability_bindings=tuple(
                CapabilityBinding(
                    capability=key,
                    provider=f"plugin.{key}",
                    cardinality="one",
                )
                for key in ("composer.brain", "composer.body", "composer.perceive")
            ),
        )
        with pytest.raises(BindPlanError, match="missing_capability"):
            bind_plan(_request(), plan, scope=_full_scope())


class TestStrictTeamBinding:
    def test_no_team_composer_fails_closed(self) -> None:
        """With no team composer declared in the plan, bind_team must
        fail-closed because the team composer binding is required."""
        with pytest.raises(BindPlanError):
            bind_team(_team_spec(), _plan(), scope=_StubScope())

    def test_agent_composers_are_not_called_while_binding_team_graph(self) -> None:
        """Only the TeamGraph composer is eligible for Team composition."""

        from lca.contracts.protocols.plan import CapabilityBinding

        plan = _plan(
            with_capability_bindings=tuple(
                CapabilityBinding(
                    capability=key,
                    provider=f"plugin.{key}",
                    cardinality="one",
                )
                for key in ("composer.brain", "composer.body", "composer.perceive", "composer.team")
            )
        )
        result = bind_team(_team_spec(), plan, scope=_full_scope())
        assert result.composer_capability == "composer.team"

    def test_complete_team_composer_returns_binding(self) -> None:
        from lca.contracts.protocols.plan import CapabilityBinding

        plan = _plan(
            with_capability_bindings=(
                CapabilityBinding(
                    capability="composer.team",
                    provider="plugin.composer.team",
                    cardinality="one",
                ),
            ),
        )
        result = bind_team(_team_spec(), plan, scope=_full_scope())
        assert isinstance(result, TeamBindingResult)
        assert result.graph.members == ("member",)
        assert result.graph.lead is None
        assert result.composer_capability == "composer.team"

    def test_team_binding_reads_the_plan_frozen_on_the_scope(self) -> None:
        """Production Team binding must not accept a second plan interpretation."""

        from lca.contracts.protocols.plan import CapabilityBinding

        plan = _plan(
            with_capability_bindings=(
                CapabilityBinding(
                    capability="composer.team",
                    provider="plugin.composer.team",
                    cardinality="one",
                ),
            ),
        )
        from lca.harness.profile.boot_products import (
            ProfileBootProducts,
            attach_profile_boot_products,
        )

        scope = _full_scope()
        attach_profile_boot_products(scope, ProfileBootProducts(compiled_run_plan=plan))

        result = bind_team_from_scope(_team_spec(), scope=scope)

        assert result.plan is plan
        assert result.composer_capability == "composer.team"


class TestDefaultProfilePlanBinding:
    @pytest.mark.asyncio
    async def test_default_profile_binds_plan_to_solo_agent(self) -> None:
        from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter
        from lca.application.api import ensure_default_ctx
        from lca.application.spawn import spawn_agent
        from tests.support.agent_specs import make_spec

        scope = await ensure_default_ctx()
        agent = spawn_agent(make_spec("plan-bound", MockLLMAdapter()), scope=scope)
        assert agent.plan_ref
        assert agent.runtime is not None

    def test_spawn_agent_exposes_no_legacy_selection_parameters(self) -> None:
        from lca.application.spawn import spawn_agent

        parameters = inspect.signature(spawn_agent).parameters
        assert "compiled_plan" not in parameters
        assert "use_bind_plan" not in parameters


def _plan(
    *,
    with_binding: bool = False,
    with_capability_bindings: tuple[Any, ...] = (),
) -> Any:
    """Construct a minimal declarative CompiledRunPlan for binding tests.

    ``with_binding=True`` populates ``capability.provider_bindings`` with a
    known-unresolvable capability so the validator exercises
    ``_validate_capability_bindings`` fail-closed path.
    ``with_capability_bindings`` populates the top-level declarative
    ``capability_bindings`` consumed by ``_composer_bindings`` to discover
    composers from the compiled plan (ADR-0074/0075 cutover).
    """
    from lca.contracts.atoms.scope import Scope
    from lca.contracts.protocols.capability_plan import CapabilityPlan, ProviderBinding
    from lca.contracts.protocols.declarative_phase_graph import (
        ActionAuthorityPlan,
        CognitivePhaseGraphPlan,
        PhaseBinding,
        PhaseNode,
        SemanticPhase,
    )
    from lca.contracts.protocols.plan import CompiledRunPlan
    from lca.contracts.protocols.scope_plan import BudgetCeiling, ScopePlan

    bindings = (
        (ProviderBinding(capability="missing_capability", owner_plugin="missing_plugin"),)
        if with_binding
        else ()
    )
    phase_graph = CognitivePhaseGraphPlan(
        entry="perceive.main",
        nodes=(
            PhaseNode(
                id="perceive.main",
                semantic_phase=SemanticPhase.PERCEIVE,
                binding="phase.perceive.standard",
                max_visits=1,
            ),
        ),
        edges=(),
    )
    phase_bindings = (
        PhaseBinding(
            node_id="perceive.main",
            semantic_phase=SemanticPhase.PERCEIVE,
            executor_capability="phase.perceive.standard",
        ),
    )
    return CompiledRunPlan(
        profile_path="test.yaml",
        capability=CapabilityPlan(
            profile_path="test.yaml", provider_bindings=bindings, relations=()
        ),
        scope=ScopePlan(
            profile_path="test.yaml",
            lifecycle=Scope.RUN,
            visibility=(Scope.RUN,),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        ),
        capability_bindings=with_capability_bindings,
        phase_graph=phase_graph,
        phase_bindings=phase_bindings,
        action_authority=ActionAuthorityPlan(
            allowed_actions=frozenset({"respond"}),
            scope="solo",
        ),
    )


def _request() -> AgentCompositionRequest:
    from unittest.mock import MagicMock

    return AgentCompositionRequest(spec=MagicMock())


def _team_spec() -> object:
    from unittest.mock import MagicMock

    return MagicMock()
