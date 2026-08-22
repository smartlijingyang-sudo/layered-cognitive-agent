"""Tests for spawn.bind_plan (ADR-0071 + ADR-0074 PR-5).

This test covers:

- Composer Protocol + AgentGraph / TeamGraph dataclasses (PR-5a data layer)
- merge_agent_graphs module-level helper (ADR-0015)
- bind_plan function: legacy fallback, capability validation
- spawn_agent with use_bind_plan=True path (compiled_plan parameter)
- bind_team: legacy fallback (PR-5b TEAM composer not yet implemented)
- is_bind_plan_available scope check
- spawn_bind_plan / composer module re-exports (harness/__init__)
"""

from __future__ import annotations

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
    BindOptions,
    BindPlanError,
    PlanBindingResult,
    TeamBindingResult,
    bind_plan,
    bind_team,
    is_bind_plan_available,
)

# ── AgentGraph / TeamGraph ──────────────────────────────────────────


class TestAgentGraph:
    def test_minimal_valid(self) -> None:
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
        assert graph.brain is None
        assert agent_graph_has_brain(graph) is False
        assert agent_graph_has_body(graph) is False
        assert graph.metadata == {}

    def test_with_metadata(self) -> None:
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
            metadata={"composer_key": "brain"},
        )
        assert graph.metadata == {"composer_key": "brain"}


class TestTeamGraph:
    def test_empty_team(self) -> None:
        graph = TeamGraph(
            members=(),
            strategy=None,
            stage=None,
            transport=None,
            observability=None,
        )
        assert graph.members == ()
        assert team_graph_member_count(graph) == 0


# ── merge_agent_graphs ──────────────────────────────────────────────


class TestMergeAgentGraphs:
    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one graph"):
            merge_agent_graphs()

    def test_single_returns_same(self) -> None:
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
        merged = merge_agent_graphs(graph)
        assert merged is graph

    def test_absent_partial_field_preserves_prior_contribution(self) -> None:
        g1 = AgentGraph(
            brain="brain1",
            body=None,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=None,
            stop_rule=None,
        )
        g2 = AgentGraph(
            brain=None,
            body="body2",
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=None,
            stop_rule=None,
        )
        merged = merge_agent_graphs(g1, g2)
        assert merged.brain == "brain1"
        assert merged.body == "body2"

    def test_later_wins_per_field(self) -> None:
        g1 = AgentGraph(
            brain="brain1",
            body=None,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=None,
            stop_rule=None,
        )
        g2 = AgentGraph(
            brain="brain2",
            body="body2",
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=None,
            stop_rule=None,
        )
        merged = merge_agent_graphs(g1, g2)
        assert merged.brain == "brain2"
        assert merged.body == "body2"


# ── bind_plan function ─────────────────────────────────────────────


class _StubScope:
    """Stub cordis Context for testing bind_plan without real boot."""

    def __init__(self, composers: dict[str, object] | None = None) -> None:
        self._composers = composers or {}

    def inject(self, key: str) -> Any:
        if key not in self._composers:
            raise KeyError(f"missing: {key}")
        return self._composers[key]


class _StubBrainComposer:
    """Returns AgentGraph with brain field populated."""

    key = "brain"

    def compose_agent(self, spec, scope):
        return AgentGraph(
            brain="stub_brain",
            body=None,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=None,
            stop_rule=None,
            metadata={"source": "brain_composer"},
        )

    def compose_team(self, spec, scope):
        raise NotImplementedError


class TestBindPlanLegacyPath:
    def test_use_legacy_spawn_emits_warning(self) -> None:
        """``use_legacy_spawn=True`` 走 fallback path 并发 DeprecationWarning。"""
        scope = _StubScope()
        plan = _make_minimal_plan()
        spec = _make_minimal_spec()
        with pytest.warns(DeprecationWarning, match="use_legacy_spawn=True"):
            result = bind_plan(spec, plan, scope=scope, options=BindOptions(use_legacy_spawn=True))
        assert result.metadata.get("legacy") is True
        from lca.contracts.protocols.plan import compiled_run_plan_ref

        assert result.plan_ref == compiled_run_plan_ref(plan)

    def test_no_composers_raises(self) -> None:
        """scope 不含 sub-composer → BindPlanError。"""
        scope = _StubScope(composers={})  # 空
        plan = _make_minimal_plan()
        spec = _make_minimal_spec()
        with pytest.raises(BindPlanError, match="no sub-composer available"):
            bind_plan(spec, plan, scope=scope)

    def test_no_inject_raises(self) -> None:
        """scope 无 inject() 方法 → BindPlanError（cordis Context required）。"""
        scope = object()  # no inject attribute
        plan = _make_minimal_plan()
        spec = _make_minimal_spec()
        with pytest.raises(BindPlanError, match="no sub-composer available"):
            bind_plan(spec, plan, scope=scope)


class TestBindPlanHappyPath:
    def test_partial_composer_succeeds(self) -> None:
        """scope 仅含 brain composer → bind_plan 用 brain graph 返回。"""
        scope = _StubScope(composers={"composer.brain": _StubBrainComposer()})
        plan = _make_minimal_plan()
        spec = _make_minimal_spec()
        result = bind_plan(spec, plan, scope=scope)
        assert isinstance(result, PlanBindingResult)
        assert result.graph.brain == "stub_brain"
        assert "brain" in result.metadata["composers_used"]
        assert "body" in result.metadata["missing_composers"]
        assert "perceive" in result.metadata["missing_composers"]

    def test_plan_ref_propagates(self) -> None:
        """PlanBindingResult.plan_ref 等于 compiled_run_plan_ref(plan)。"""
        scope = _StubScope(composers={"composer.brain": _StubBrainComposer()})
        plan = _make_minimal_plan()
        result = bind_plan(plan=plan, spec=_make_minimal_spec(), scope=scope)
        from lca.contracts.protocols.plan import compiled_run_plan_ref

        assert result.plan_ref == compiled_run_plan_ref(plan)

    def test_disable_capability_validation_skips_check(self) -> None:
        """``enforce_capability_plan=False`` 跳过 capability 校验。"""
        scope = _StubScope(composers={"composer.brain": _StubBrainComposer()})
        plan = _make_minimal_plan_with_bindings()  # 含未注册的 capability
        # 应该不抛异常
        result = bind_plan(
            spec=_make_minimal_spec(),
            plan=plan,
            scope=scope,
            options=BindOptions(enforce_capability_plan=False),
        )
        assert result is not None


# ── bind_team (legacy fallback) ─────────────────────────────────────


class TestBindTeamLegacy:
    def test_bind_team_falls_back_to_legacy(self) -> None:
        """TEAM composer 未实现 → bind_team 退化到 _legacy_bind_team + warning。"""
        scope = _StubScope()
        plan = _make_minimal_plan()
        spec = _make_minimal_team_spec()
        with pytest.warns(DeprecationWarning, match="TEAM composer not yet implemented"):
            result = bind_team(spec, plan, scope=scope)
        assert isinstance(result, TeamBindingResult)
        assert result.metadata.get("legacy") is True


# ── is_bind_plan_available ─────────────────────────────────────────


class TestIsBindPlanAvailable:
    def test_empty_scope_returns_false(self) -> None:
        assert is_bind_plan_available(_StubScope(composers={})) is False

    def test_partial_scope_returns_false(self) -> None:
        """Only brain composer → not all 3 composers present."""
        scope = _StubScope(composers={"composer.brain": _StubBrainComposer()})
        assert is_bind_plan_available(scope) is False

    def test_full_scope_returns_true(self) -> None:
        scope = _StubScope(
            composers={
                "composer.brain": _StubBrainComposer(),
                "composer.body": _StubBrainComposer(),  # reuse stub for test
                "composer.perceive": _StubBrainComposer(),
            }
        )
        assert is_bind_plan_available(scope) is True

    def test_no_inject_returns_false(self) -> None:
        assert is_bind_plan_available(object()) is False


# ── spawn_agent integration ─────────────────────────────────────────


class TestDefaultProfilePlanBinding:
    @pytest.mark.asyncio
    async def test_default_profile_binds_compiled_plan_to_solo_agent(self) -> None:
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from lca.layer4_app.api import ensure_default_ctx
        from lca.layer4_app.spawn import spawn_agent
        from tests.support.agent_specs import make_spec

        scope = await ensure_default_ctx()
        agent = spawn_agent(make_spec("plan-bound", MockLLMAdapter()), scope=scope)

        assert agent.plan_ref
        assert agent.runtime is not None


class TestSpawnAgentBindPlanKwarg:
    """spawn_agent 接受 compiled_plan + use_bind_plan kwarg (PR-5 signature)。

    当 ``use_bind_plan=True`` 且 sub-composers 不存在时 → warning +
    走 legacy 路径；当 compiled_plan 未提供 → 直接走 legacy。
    """

    def test_spawn_agent_signature_accepts_compiled_plan(self) -> None:
        """``spawn_agent`` 接受 compiled_plan / use_bind_plan kwargs。"""
        import inspect

        from lca.layer4_app.spawn import spawn_agent

        sig = inspect.signature(spawn_agent)
        assert "compiled_plan" in sig.parameters
        assert "use_bind_plan" in sig.parameters
        assert sig.parameters["compiled_plan"].default is None
        assert sig.parameters["use_bind_plan"].default is False


# ── Test helpers ─────────────────────────────────────────────────────


def _make_minimal_plan(plan_ref: str = "0123456789abcdef") -> Any:
    """Build a minimal real CompiledRunPlan for testing.

    Uses the actual CompiledRunPlan dataclass to ensure plan_ref is
    hashable + JSON-serializable (avoid MagicMock json errors).
    """
    from lca.contracts.atoms.scope import Scope
    from lca.contracts.protocols.capability_plan import CapabilityPlan
    from lca.contracts.protocols.control_plan import ControlPlan
    from lca.contracts.protocols.plan import CompiledRunPlan
    from lca.contracts.protocols.scope_plan import BudgetCeiling, ScopePlan

    capability = CapabilityPlan(profile_path="test.yaml", provider_bindings=(), relations=())
    control = ControlPlan(profile_path="test.yaml", entries=(), by_slot={}, plan_hash="0" * 16)
    scope = ScopePlan(
        profile_path="test.yaml",
        lifecycle=Scope.RUN,
        visibility=(Scope.RUN,),
        acl_grants=(),
        budget_ceiling=BudgetCeiling(),
    )
    # Compute plan_ref manually (call compiled_run_plan_ref)

    plan = CompiledRunPlan(
        profile_path="test.yaml",
        capability=capability,
        control=control,
        scope=scope,
    )
    # Override plan_ref via attribute (CompiledRunPlan uses module-level fn)
    return plan


def _make_minimal_plan_with_bindings() -> Any:
    """Plan with capability bindings (some unresolvable)."""
    from lca.contracts.atoms.scope import Scope
    from lca.contracts.protocols.capability_plan import (
        CapabilityPlan,
        ProviderBinding,
    )
    from lca.contracts.protocols.control_plan import ControlPlan
    from lca.contracts.protocols.plan import CompiledRunPlan
    from lca.contracts.protocols.scope_plan import BudgetCeiling, ScopePlan

    capability = CapabilityPlan(
        profile_path="test.yaml",
        provider_bindings=(
            ProviderBinding(
                capability="missing_capability",
                owner_plugin="missing_plugin",
            ),
        ),
        relations=(),
    )
    control = ControlPlan(profile_path="test.yaml", entries=(), by_slot={}, plan_hash="0" * 16)
    scope = ScopePlan(
        profile_path="test.yaml",
        lifecycle=Scope.RUN,
        visibility=(Scope.RUN,),
        acl_grants=(),
        budget_ceiling=BudgetCeiling(),
    )
    return CompiledRunPlan(
        profile_path="test.yaml",
        capability=capability,
        control=control,
        scope=scope,
    )


def _make_minimal_spec() -> object:
    """Build a minimal AgentSpec-like object."""
    from unittest.mock import MagicMock

    spec = MagicMock()
    return spec


def _make_minimal_team_spec() -> object:
    """Build a minimal TeamSpec-like object."""
    from unittest.mock import MagicMock

    spec = MagicMock()
    return spec
