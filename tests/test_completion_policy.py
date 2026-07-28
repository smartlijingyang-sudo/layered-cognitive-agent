"""DelegationLedger + CompletionPolicy + GuardedTaskCoordinator 单元测试。"""

from __future__ import annotations

import pytest

from lca.contracts.decision import DelegationSpec, StructuredDecision
from lca.contracts.state import Budget, TypedState
from lca.contracts.team_progress import (
    DelegationLedger,
    ledger_tracking_hook,
    progress_injection_hook,
)
from lca.layer1_cognitive.brain.completion_policies.roster_coverage import (
    RosterCoveragePolicy,
)
from lca.layer1_cognitive.brain.guarded_coordinator import GuardedTaskCoordinator

# ── helpers ──


def _state(task: str = "test task", **kw) -> TypedState:
    return TypedState(trace_id="t", task=task, budget=Budget(), **kw)


def _decision(action_type: str = "respond", **kw) -> StructuredDecision:
    return StructuredDecision(
        decision_id="d1",
        action_type=action_type,
        rationale="test",
        confidence=0.9,
        **kw,
    )


def _ledger(roles: set[str], status: dict[str, str] | None = None) -> DelegationLedger:
    return DelegationLedger(
        mandatory_roles=frozenset(roles),
        status=status or dict.fromkeys(roles, "pending"),
    )


# ── DelegationLedger ──


class TestDelegationLedger:
    def test_auto_init_pending(self) -> None:
        ledger = _ledger({"a", "b"})
        assert ledger.status["a"] == "pending"
        assert ledger.status["b"] == "pending"

    def test_is_covered_false_when_pending(self) -> None:
        ledger = _ledger({"a", "b"})
        assert ledger.is_covered() is False

    def test_is_covered_true_when_all_done(self) -> None:
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "done"})
        assert ledger.is_covered() is True

    def test_is_covered_partial(self) -> None:
        ledger = _ledger({"a", "b", "c"}, {"a": "done", "b": "done", "c": "pending"})
        assert ledger.is_covered() is False

    def test_pending_roles(self) -> None:
        ledger = _ledger({"a", "b", "c"}, {"a": "done", "b": "pending", "c": "failed"})
        pending = ledger.pending_roles()
        assert set(pending) == {"b", "c"}

    def test_mark_returns_new_instance(self) -> None:
        ledger = _ledger({"a", "b"})
        new_ledger = ledger.mark("a", "done")
        assert new_ledger is not ledger
        assert new_ledger.status["a"] == "done"
        assert ledger.status["a"] == "pending"  # original unchanged

    def test_mark_chain(self) -> None:
        ledger = _ledger({"a", "b"})
        ledger = ledger.mark("a", "done").mark("b", "done")
        assert ledger.is_covered() is True


# ── RosterCoveragePolicy ──


class TestRosterCoveragePolicy:
    @pytest.mark.asyncio
    async def test_respond_blocked_when_not_covered(self) -> None:
        ledger = _ledger({"analyst", "reviewer"})
        state = _state(team_progress=ledger)
        policy = RosterCoveragePolicy()

        decision = _decision("respond")
        result = await policy.enforce(state, decision)

        assert result.action_type == "delegate"
        assert result.delegate_to is not None
        assert result.delegate_to.target_role in {"analyst", "reviewer"}
        assert "[框架强制]" in result.rationale
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_respond_allowed_when_covered(self) -> None:
        ledger = _ledger({"a"}, {"a": "done"})
        state = _state(team_progress=ledger)
        policy = RosterCoveragePolicy()

        decision = _decision("respond")
        result = await policy.enforce(state, decision)

        assert result.action_type == "respond"

    @pytest.mark.asyncio
    async def test_delegate_passes_through(self) -> None:
        ledger = _ledger({"a", "b"})
        state = _state(team_progress=ledger)
        policy = RosterCoveragePolicy()

        decision = _decision(
            "delegate",
            delegate_to=DelegationSpec(target_role="a", subtask="do stuff"),
        )
        result = await policy.enforce(state, decision)

        assert result.action_type == "delegate"
        assert result.delegate_to.target_role == "a"

    @pytest.mark.asyncio
    async def test_no_ledger_passes_through(self) -> None:
        state = _state()  # team_progress=None
        policy = RosterCoveragePolicy()

        decision = _decision("respond")
        result = await policy.enforce(state, decision)

        assert result.action_type == "respond"

    @pytest.mark.asyncio
    async def test_subtask_includes_role_and_task(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(task="launch product", team_progress=ledger)
        policy = RosterCoveragePolicy()

        result = await policy.enforce(state, _decision("respond"))

        assert result.delegate_to is not None
        assert "analyst" in result.delegate_to.subtask
        assert "launch product" in result.delegate_to.subtask


# ── GuardedTaskCoordinator ──


class TestGuardedTaskCoordinator:
    @pytest.mark.asyncio
    async def test_wraps_inner_coordinator(self) -> None:
        from lca.layer1_cognitive.brain.map_modules import SimpleTaskCoordinator

        inner = SimpleTaskCoordinator()
        policy = RosterCoveragePolicy()
        guarded = GuardedTaskCoordinator(inner, policy)

        ledger = _ledger({"a"})  # all pending
        state = _state(team_progress=ledger)

        candidates = [_decision("respond")]
        scores = [0.9]

        result = await guarded.arbitrate(state, candidates, scores)

        # Inner picks respond (best score), but policy overrides to delegate
        assert result.action_type == "delegate"

    @pytest.mark.asyncio
    async def test_passes_through_when_covered(self) -> None:
        from lca.layer1_cognitive.brain.map_modules import SimpleTaskCoordinator

        inner = SimpleTaskCoordinator()
        policy = RosterCoveragePolicy()
        guarded = GuardedTaskCoordinator(inner, policy)

        ledger = _ledger({"a"}, {"a": "done"})
        state = _state(team_progress=ledger)

        candidates = [_decision("respond")]
        scores = [0.9]

        result = await guarded.arbitrate(state, candidates, scores)

        assert result.action_type == "respond"


# ── Hooks ──


class TestLedgerTrackingHook:
    @pytest.mark.asyncio
    async def test_marks_done_on_success(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(team_progress=ledger)

        decision = _decision(
            "delegate",
            delegate_to=DelegationSpec(target_role="analyst", subtask="analyze"),
        )
        from lca.contracts.decision import Observation

        obs = Observation(observation_id="o1", success=True, payload="ok")

        await ledger_tracking_hook("post_act", state, decision=decision, observation=obs)

        assert state.team_progress is not None
        assert state.team_progress.status["analyst"] == "done"

    @pytest.mark.asyncio
    async def test_marks_failed_on_error(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(team_progress=ledger)

        decision = _decision(
            "delegate",
            delegate_to=DelegationSpec(target_role="analyst", subtask="analyze"),
        )
        from lca.contracts.decision import Observation

        obs = Observation(observation_id="o1", success=False, payload=None, error="boom")

        await ledger_tracking_hook("post_act", state, decision=decision, observation=obs)

        assert state.team_progress is not None
        assert state.team_progress.status["analyst"] == "failed"

    @pytest.mark.asyncio
    async def test_noop_when_no_ledger(self) -> None:
        state = _state()  # no team_progress
        decision = _decision("delegate")
        await ledger_tracking_hook("post_act", state, decision=decision)
        # Should not raise

    @pytest.mark.asyncio
    async def test_noop_for_respond(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(team_progress=ledger)
        decision = _decision("respond")
        await ledger_tracking_hook("post_act", state, decision=decision)
        assert state.team_progress.status["analyst"] == "pending"


class TestProgressInjectionHook:
    @pytest.mark.asyncio
    async def test_injects_pending_roles(self) -> None:
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "pending"})
        state = _state(team_progress=ledger)

        await progress_injection_hook("pre_think", state)

        assert "b" in state.working_memory["team_progress_text"]

    @pytest.mark.asyncio
    async def test_injects_all_done(self) -> None:
        ledger = _ledger({"a"}, {"a": "done"})
        state = _state(team_progress=ledger)

        await progress_injection_hook("pre_think", state)

        assert "完毕" in state.working_memory["team_progress_text"]

    @pytest.mark.asyncio
    async def test_noop_when_no_ledger(self) -> None:
        state = _state()
        await progress_injection_hook("pre_think", state)
        assert "team_progress_text" not in state.working_memory
