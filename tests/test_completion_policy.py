"""InMemoryMemberStatus + DecisionGate 单元测试。"""

from __future__ import annotations

import pytest

from lca.contracts.decision import Decision, DelegationSpec
from lca.contracts.state import AgentState, Budget
from lca.layer1_cognitive.brain.decision_gates.must_consult_all import (
    MustConsultAllMembers,
)
from lca.layer1_cognitive.team_progress import InMemoryMemberStatus
from lca.layer1_cognitive.team_progress.progress_hooks import (
    ledger_tracking_hook,
)

# ── helpers ──


def _state(task: str = "test task", **kw) -> AgentState:
    return AgentState(trace_id="t", task=task, budget=Budget(), **kw)


def _decision(action_type: str = "respond", **kw) -> Decision:
    return Decision(
        decision_id="d1",
        action_type=action_type,
        rationale="test",
        confidence=0.9,
        **kw,
    )


def _ledger(roles: set[str], status: dict[str, str] | None = None) -> InMemoryMemberStatus:
    return InMemoryMemberStatus(
        required_roles=frozenset(roles),
        status=status or dict.fromkeys(roles, "pending"),
    )


# ── InMemoryMemberStatus ──


class TestInMemoryMemberStatus:
    def test_auto_init_pending(self) -> None:
        ledger = _ledger({"a", "b"})
        assert ledger.status["a"] == "pending"
        assert ledger.status["b"] == "pending"

    def test_is_covered_false_when_pending(self) -> None:
        ledger = _ledger({"a", "b"})
        assert ledger.all_done() is False

    def test_is_covered_true_when_all_done(self) -> None:
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "done"})
        assert ledger.all_done() is True

    def test_is_covered_partial(self) -> None:
        ledger = _ledger({"a", "b", "c"}, {"a": "done", "b": "done", "c": "pending"})
        assert ledger.all_done() is False

    def test_pending_roles(self) -> None:
        ledger = _ledger({"a", "b", "c"}, {"a": "done", "b": "pending", "c": "failed"})
        pending = ledger.waiting_roles()
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
        assert ledger.all_done() is True


# ── MustConsultAllMembers ──


class TestMustConsultAllMembers:
    @pytest.mark.asyncio
    async def test_respond_blocked_when_not_covered(self) -> None:
        ledger = _ledger({"analyst", "reviewer"})
        state = _state(member_status=ledger)
        policy = MustConsultAllMembers()

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
        state = _state(member_status=ledger)
        policy = MustConsultAllMembers()

        decision = _decision("respond")
        result = await policy.enforce(state, decision)

        assert result.action_type == "respond"

    @pytest.mark.asyncio
    async def test_delegate_passes_through(self) -> None:
        ledger = _ledger({"a", "b"})
        state = _state(member_status=ledger)
        policy = MustConsultAllMembers()

        decision = _decision(
            "delegate",
            delegate_to=DelegationSpec(target_role="a", subtask="do stuff"),
        )
        result = await policy.enforce(state, decision)

        assert result.action_type == "delegate"
        assert result.delegate_to.target_role == "a"

    @pytest.mark.asyncio
    async def test_no_ledger_passes_through(self) -> None:
        state = _state()  # member_status=None
        policy = MustConsultAllMembers()

        decision = _decision("respond")
        result = await policy.enforce(state, decision)

        assert result.action_type == "respond"

    @pytest.mark.asyncio
    async def test_subtask_includes_role_and_task(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(task="launch product", member_status=ledger)
        policy = MustConsultAllMembers()

        result = await policy.enforce(state, _decision("respond"))

        assert result.delegate_to is not None
        assert "analyst" in result.delegate_to.subtask
        assert "launch product" in result.delegate_to.subtask


# ── Hooks ──


class TestLedgerTrackingHook:
    @pytest.mark.asyncio
    async def test_marks_done_on_success(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(member_status=ledger)

        decision = _decision(
            "delegate",
            delegate_to=DelegationSpec(target_role="analyst", subtask="analyze"),
        )
        from lca.contracts.decision import Observation

        obs = Observation(observation_id="o1", success=True, payload="ok")

        await ledger_tracking_hook("post_act", state, decision=decision, observation=obs)

        assert state.member_status is not None
        assert state.member_status.status["analyst"] == "done"

    @pytest.mark.asyncio
    async def test_marks_failed_on_error(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(member_status=ledger)

        decision = _decision(
            "delegate",
            delegate_to=DelegationSpec(target_role="analyst", subtask="analyze"),
        )
        from lca.contracts.decision import Observation

        obs = Observation(observation_id="o1", success=False, payload=None, error="boom")

        await ledger_tracking_hook("post_act", state, decision=decision, observation=obs)

        assert state.member_status is not None
        assert state.member_status.status["analyst"] == "failed"

    @pytest.mark.asyncio
    async def test_noop_when_no_ledger(self) -> None:
        state = _state()  # no team_progress
        decision = _decision("delegate")
        await ledger_tracking_hook("post_act", state, decision=decision)
        # Should not raise

    @pytest.mark.asyncio
    async def test_noop_for_respond(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(member_status=ledger)
        decision = _decision("respond")
        await ledger_tracking_hook("post_act", state, decision=decision)
        assert state.member_status.status["analyst"] == "pending"


class TestMemberStatusPromptText:
    def test_waiting_roles_text(self) -> None:
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "pending"})
        text = ledger.as_prompt_text()
        assert "b" in text

    def test_all_done_text(self) -> None:
        ledger = _ledger({"a"}, {"a": "done"})
        text = ledger.as_prompt_text()
        assert "完毕" in text

    def test_reasoner_uses_as_prompt_text_not_state_field(self) -> None:
        """Prompt text is derived; AgentState has no cached progress field."""
        state = _state()
        assert not hasattr(state, "team_progress_text")
        assert not hasattr(state, "MEMBER_STATUS_PROMPT_REMOVED")
