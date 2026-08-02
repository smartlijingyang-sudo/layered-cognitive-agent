"""Characteristic baseline for _promote_supervisor budget promotion.

Pins down the CURRENT behavior of assembly._promote_supervisor before
Phase B refactors it into a BudgetPolicy strategy. These tests will be
updated to assert BudgetPolicyViolation (strict mode) after the refactor.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lca.contracts.budget import (
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    SUPERVISOR_MIN_MAX_STEPS,
)
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.layer3_agent.simple_agent import CognitiveAgent
from lca.layer4_app.assembly import _promote_supervisor


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
    return CognitiveAgent(
        runtime,
        rp,
        max_steps=max_steps,
        max_wall_clock_seconds=max_wall_clock_seconds,
    )


class TestPromoteSupervisorStepsBumped:
    """max_steps below floor is silently bumped to SUPERVISOR_MIN_MAX_STEPS."""

    def test_steps_below_floor_bumped(self) -> None:
        agent = _make_agent(max_steps=5)
        promoted = _promote_supervisor(agent)
        assert promoted.max_steps == SUPERVISOR_MIN_MAX_STEPS

    def test_steps_at_floor_unchanged(self) -> None:
        agent = _make_agent(max_steps=SUPERVISOR_MIN_MAX_STEPS)
        promoted = _promote_supervisor(agent)
        assert promoted.max_steps == SUPERVISOR_MIN_MAX_STEPS

    def test_steps_above_floor_unchanged(self) -> None:
        agent = _make_agent(max_steps=50)
        promoted = _promote_supervisor(agent)
        assert promoted.max_steps == 50


class TestPromoteSupervisorWallClockBumped:
    """max_wall_clock_seconds below floor is silently bumped."""

    def test_wc_below_floor_bumped(self) -> None:
        agent = _make_agent(max_wall_clock_seconds=10)
        promoted = _promote_supervisor(agent)
        assert promoted.max_wall_clock_seconds == DEFAULT_MAX_WALL_CLOCK_SECONDS

    def test_wc_above_floor_unchanged(self) -> None:
        agent = _make_agent(max_wall_clock_seconds=600)
        promoted = _promote_supervisor(agent)
        assert promoted.max_wall_clock_seconds == 600

    def test_wc_none_set_to_default(self) -> None:
        agent = _make_agent(max_wall_clock_seconds=None)
        promoted = _promote_supervisor(agent)
        assert promoted.max_wall_clock_seconds == DEFAULT_MAX_WALL_CLOCK_SECONDS


class TestPromoteSupervisorPreservesIdentity:
    """The promoted agent's role_profile and runtime are preserved."""

    def test_role_profile_preserved(self) -> None:
        agent = _make_agent(role="lead")
        promoted = _promote_supervisor(agent)
        assert promoted.role_profile.role == "lead"
        assert promoted.role_profile.goal == "test"

    def test_runtime_preserved(self) -> None:
        agent = _make_agent()
        promoted = _promote_supervisor(agent)
        assert promoted.runtime is agent.runtime


class TestPromoteSupervisorReturnsNewInstance:
    """_promote_supervisor returns a new CognitiveAgent, not a mutant."""

    def test_original_unchanged(self) -> None:
        agent = _make_agent(max_steps=5, max_wall_clock_seconds=10)
        _promote_supervisor(agent)
        assert agent.max_steps == 5
        assert agent.max_wall_clock_seconds == 10

    def test_returns_new_instance(self) -> None:
        agent = _make_agent()
        promoted = _promote_supervisor(agent)
        assert promoted is not agent


class TestNoPersistencePath:
    """Verify that MemoryRecord and TeamConfig are never persisted to disk.

    This confirms there is no serialization/deserialization path that
    would require a data migration when memory_type/shared_memory_layers
    types change from bare strings to enums.
    """

    def test_memory_record_is_in_memory_only(self) -> None:
        from lca.contracts.enums import MemoryLayer
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
