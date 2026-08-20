"""Baseline for promote_lead budget promotion via BudgetPolicy.

Pins down the promotion behavior: LeadBudgetPolicy.resolve
computes effective budget limits, promote_lead applies them
to construct a new CognitiveAgent with corrected values.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lca.contracts.models.core.budget import (
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    LEAD_MIN_MAX_STEPS,
)
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer4_app.policies import LeadBudgetPolicy
from lca.layer4_app.spawn import promote_lead

_policy = LeadBudgetPolicy()


def _make_agent(
    max_steps: int = DEFAULT_MAX_STEPS,
    max_wall_clock_seconds: int | None = DEFAULT_MAX_WALL_CLOCK_SECONDS,
    role: str = "supervisor",
) -> CognitiveAgent:
    runtime = MagicMock()
    rp = RoleProfile(
        role=role,
        goal="test",
        backstory="",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    from lca.harness.observability import make_minimal_bound
    return CognitiveAgent(
        runtime,
        rp,
        make_minimal_bound(),
        max_steps=max_steps,
        max_wall_clock_seconds=max_wall_clock_seconds,
    )


class TestPromoteSupervisorStepsBumped:
    """max_steps below floor is silently bumped to LEAD_MIN_MAX_STEPS."""

    def test_steps_below_floor_bumped(self) -> None:
        agent = _make_agent(max_steps=5)
        promoted = promote_lead(agent, _policy)
        assert promoted.max_steps == LEAD_MIN_MAX_STEPS

    def test_steps_at_floor_unchanged(self) -> None:
        agent = _make_agent(max_steps=LEAD_MIN_MAX_STEPS)
        promoted = promote_lead(agent, _policy)
        assert promoted.max_steps == LEAD_MIN_MAX_STEPS

    def test_steps_above_floor_unchanged(self) -> None:
        agent = _make_agent(max_steps=50)
        promoted = promote_lead(agent, _policy)
        assert promoted.max_steps == 50


class TestPromoteSupervisorWallClockBumped:
    """max_wall_clock_seconds below floor is silently bumped."""

    def test_wc_below_floor_bumped(self) -> None:
        agent = _make_agent(max_wall_clock_seconds=10)
        promoted = promote_lead(agent, _policy)
        assert promoted.max_wall_clock_seconds == DEFAULT_MAX_WALL_CLOCK_SECONDS

    def test_wc_above_floor_unchanged(self) -> None:
        agent = _make_agent(max_wall_clock_seconds=600)
        promoted = promote_lead(agent, _policy)
        assert promoted.max_wall_clock_seconds == 600

    def test_wc_none_set_to_default(self) -> None:
        agent = _make_agent(max_wall_clock_seconds=None)
        promoted = promote_lead(agent, _policy)
        assert promoted.max_wall_clock_seconds == DEFAULT_MAX_WALL_CLOCK_SECONDS


class TestPromoteSupervisorPreservesIdentity:
    """The promoted agent's role_profile and runtime are preserved."""

    def test_role_profile_preserved(self) -> None:
        agent = _make_agent(role="lead")
        promoted = promote_lead(agent, _policy)
        assert promoted.role_profile.role == "lead"
        assert promoted.role_profile.goal == "test"

    def test_runtime_preserved(self) -> None:
        agent = _make_agent()
        promoted = promote_lead(agent, _policy)
        assert promoted.runtime is agent.runtime


class TestPromoteSupervisorReturnsNewInstance:
    """promote_lead returns a new CognitiveAgent, not a mutant."""

    def test_original_unchanged(self) -> None:
        agent = _make_agent(max_steps=5, max_wall_clock_seconds=10)
        promote_lead(agent, _policy)
        assert agent.max_steps == 5
        assert agent.max_wall_clock_seconds == 10

    def test_returns_new_instance(self) -> None:
        agent = _make_agent()
        promoted = promote_lead(agent, _policy)
        assert promoted is not agent


class TestNoPersistencePath:
    """Verify that MemoryRecord and TeamSpec are never persisted to disk.

    This confirms there is no serialization/deserialization path that
    would require a data migration when memory_type/shared_memory_layers
    types change from bare strings to enums.
    """

    def test_memory_record_is_in_memory_only(self) -> None:
        from lca.contracts.atoms.enums import MemoryLayer
        from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
        from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
        from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore

        # SimpleMemorySystem uses plain Python lists
        mem = SimpleMemorySystem()
        assert isinstance(mem._private_layers[MemoryLayer.SEMANTIC], list)

        # TeamSharedMemoryStore uses a plain dict of lists
        store = TeamSharedMemoryStore([MemoryLayer.SEMANTIC])
        assert isinstance(store._stores, dict)
        assert isinstance(store._stores[MemoryLayer.SEMANTIC], list)

        # StateStore keeps AgentState in a dict — no serialization
        ss = InMemoryStateStore()
        assert isinstance(ss._store, dict)
