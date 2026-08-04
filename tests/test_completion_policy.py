"""InMemoryMemberStatus + DecisionGate + tracking 单元测试。"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.contracts.agent_spec import DEFAULT_DELEGATE_MAX_ATTEMPTS
from lca.contracts.decision import Decision, DelegationSpec, Observation
from lca.contracts.enums import RoleStatus
from lca.contracts.ids import elapsed_seconds, remaining_seconds, utc_now
from lca.contracts.protocols import SupportsShortcut
from lca.contracts.role_status_rules import is_success_status, is_terminal_status
from lca.contracts.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.state import AgentState, Budget
from lca.contracts.team_awareness import Settlement, TeamAwareness
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.decision_gates.must_consult_all import (
    MustConsultAllMembers,
)
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.member_status import (
    InMemoryMemberStatus,
    compute_required_action,
    settle_delegation,
)
from lca.layer1_cognitive.member_status.tracking import _next_role_status

# ── helpers ──


def _state(task: str = "test task", **kw) -> AgentState:
    if "member_status" in kw and "team_awareness" not in kw:
        board = kw.pop("member_status")
        if board is not None:
            kw["team_awareness"] = TeamAwareness(
                settlement=Settlement(
                    member_status=board, max_attempts=DEFAULT_DELEGATE_MAX_ATTEMPTS
                )
            )
    return AgentState(trace_id="t", task=task, budget=Budget(), **kw)


def _settlement(state: AgentState) -> Settlement | None:
    return state.team_awareness.settlement if state.team_awareness else None


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
        role_order=tuple(roles),
        status=status or dict.fromkeys(roles, "pending"),
    )


def _obs(success: bool = True, error: str = "", *, failure_kind: str | None = None) -> Observation:
    extra: dict[str, str] = {}
    if failure_kind is not None:
        extra[FAILURE_KIND] = failure_kind
    return Observation(
        observation_id="o1",
        success=success,
        payload=None if not success else "ok",
        error=error or None,
        extra=extra,
    )


# ── InMemoryMemberStatus ──


class TestInMemoryMemberStatus:
    def test_auto_init_pending(self) -> None:
        ledger = _ledger({"a", "b"})
        assert ledger.status["a"] == "pending"
        assert ledger.status["b"] == "pending"

    def test_all_done_false_when_pending(self) -> None:
        ledger = _ledger({"a", "b"})
        assert ledger.all_done() is False

    def test_all_done_true_when_all_done(self) -> None:
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "done"})
        assert ledger.all_done() is True

    def test_all_done_partial(self) -> None:
        ledger = _ledger({"a", "b", "c"}, {"a": "done", "b": "done", "c": "pending"})
        assert ledger.all_done() is False

    def test_all_settled_false_when_pending(self) -> None:
        ledger = _ledger({"a", "b"})
        assert ledger.all_settled() is False

    def test_all_settled_true_when_all_terminal(self) -> None:
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "failed"})
        assert ledger.all_settled() is True

    def test_all_settled_false_when_in_progress(self) -> None:
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "in_progress"})
        assert ledger.all_settled() is False

    def test_waiting_roles_excludes_terminal(self) -> None:
        """FAILED roles no longer appear in waiting_roles (Fix A)."""
        ledger = _ledger(
            {"a", "b", "c"},
            {"a": "done", "b": "pending", "c": "failed"},
        )
        waiting = ledger.waiting_roles()
        assert set(waiting) == {"b"}

    def test_waiting_roles_order_deterministic(self) -> None:
        """Same role_order → same iteration order (Fix D)."""
        order = ("x", "y", "z")
        for _ in range(10):
            ledger = InMemoryMemberStatus(role_order=order)
            assert ledger.waiting_roles() == ["x", "y", "z"]

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

    def test_duplicate_role_order_raises(self) -> None:
        with pytest.raises(ValueError, match="重复"):
            InMemoryMemberStatus(role_order=("a", "a"))


# ── as_prompt_text ──


class TestMemberStatusPromptText:
    def test_waiting_roles_text(self) -> None:
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "pending"})
        text = ledger.as_prompt_text()
        assert "b" in text

    def test_all_done_text(self) -> None:
        ledger = _ledger({"a"}, {"a": "done"})
        text = ledger.as_prompt_text()
        assert "完毕" in text

    def test_failed_roles_disclosed(self) -> None:
        """Fix 5: honest disclosure of permanently failed roles."""
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "failed"})
        text = ledger.as_prompt_text()
        assert "b" in text
        assert "不可用" in text

    def test_reasoner_uses_as_prompt_text_not_state_field(self) -> None:
        """Prompt text is derived; AgentState has no cached progress field."""
        state = _state()
        assert not hasattr(state, "team_progress_text")
        assert not hasattr(state, "MEMBER_STATUS_PROMPT_REMOVED")


# ── MustConsultAllMembers ──


class TestMustConsultAllMembers:
    @pytest.mark.asyncio
    async def test_respond_blocked_when_not_settled(self) -> None:
        ledger = _ledger({"analyst", "reviewer"})
        state = _state(member_status=ledger)
        policy = MustConsultAllMembers()

        decision = _decision("respond")
        result = await policy.enforce(state, decision)

        assert result.action_type == "delegate"
        assert result.delegations
        assert result.delegations[0].target_role in {"analyst", "reviewer"}
        assert "[框架强制]" in result.rationale
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_respond_allowed_when_settled_with_failures(self) -> None:
        """Degradation by design: may respond when all settled even if some failed."""
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "failed"})
        state = _state(member_status=ledger)
        policy = MustConsultAllMembers()

        decision = _decision("respond")
        result = await policy.enforce(state, decision)

        assert result.action_type == "respond"

    @pytest.mark.asyncio
    async def test_respond_allowed_when_all_done(self) -> None:
        ledger = _ledger({"a"}, {"a": "done"})
        state = _state(member_status=ledger)
        policy = MustConsultAllMembers()

        decision = _decision("respond")
        result = await policy.enforce(state, decision)

        assert result.action_type == "respond"

    @pytest.mark.asyncio
    async def test_delegate_to_waiting_role_passes_through(self) -> None:
        ledger = _ledger({"a", "b"})
        state = _state(member_status=ledger)
        policy = MustConsultAllMembers()

        decision = _decision(
            "delegate",
            delegations=[DelegationSpec(target_role="a", subtask="do stuff")],
        )
        result = await policy.enforce(state, decision)

        assert result.action_type == "delegate"
        assert result.delegations[0].target_role == "a"

    @pytest.mark.asyncio
    async def test_delegate_to_settled_role_redirected(self) -> None:
        """Fix C: gate intercepts DELEGATE to already-settled role."""
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "pending"})
        state = _state(member_status=ledger)
        policy = MustConsultAllMembers()

        decision = _decision(
            "delegate",
            delegations=[DelegationSpec(target_role="a", subtask="re-do")],
        )
        result = await policy.enforce(state, decision)

        assert result.action_type == "delegate"
        assert result.delegations[0].target_role == "b"

    @pytest.mark.asyncio
    async def test_delegate_to_failed_role_redirected(self) -> None:
        """FAILED role is settled; gate redirects to remaining waiting role."""
        ledger = _ledger({"a", "b", "c"}, {"a": "done", "b": "failed", "c": "pending"})
        state = _state(member_status=ledger)
        policy = MustConsultAllMembers()

        decision = _decision(
            "delegate",
            delegations=[DelegationSpec(target_role="b", subtask="retry")],
        )
        result = await policy.enforce(state, decision)

        assert result.action_type == "delegate"
        assert result.delegations[0].target_role == "c"

    @pytest.mark.asyncio
    async def test_delegate_when_all_settled_rewritten_to_respond(self) -> None:
        """All settled → gate rewrites DELEGATE to RESPOND."""
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "failed"})
        state = _state(member_status=ledger)
        policy = MustConsultAllMembers()

        decision = _decision(
            "delegate",
            delegations=[DelegationSpec(target_role="a", subtask="redo")],
        )
        result = await policy.enforce(state, decision)

        assert result.action_type == "respond"

    @pytest.mark.asyncio
    async def test_no_ledger_passes_through(self) -> None:
        state = _state()  # member_status=None
        policy = MustConsultAllMembers()

        decision = _decision("respond")
        result = await policy.enforce(state, decision)

        assert result.action_type == "respond"

    @pytest.mark.asyncio
    async def test_handoff_passes_through(self) -> None:
        """HANDOFF is out-of-scope; gate does not intercept."""
        ledger = _ledger({"a", "b"})
        state = _state(member_status=ledger)
        policy = MustConsultAllMembers()

        decision = _decision(
            "handoff",
            delegations=[DelegationSpec(target_role="a", subtask="handoff")],
        )
        result = await policy.enforce(state, decision)

        assert result.action_type == "handoff"

    @pytest.mark.asyncio
    async def test_subtask_includes_role_and_task(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(task="launch product", member_status=ledger)
        policy = MustConsultAllMembers()

        result = await policy.enforce(state, _decision("respond"))

        assert result.delegations
        assert "analyst" in result.delegations[0].subtask
        assert "launch product" in result.delegations[0].subtask


# ── MustConsultAllMembers.try_shortcut ──


class TestMustConsultAllMembersTryShortcut:
    @pytest.mark.asyncio
    async def test_short_circuits_when_exactly_one_waiting(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(member_status=ledger)
        result = await MustConsultAllMembers().try_shortcut(state)

        assert result is not None
        assert result.action_type == "delegate"
        assert result.delegations
        assert result.delegations[0].target_role == "analyst"
        assert "[框架短路]" in result.rationale

    @pytest.mark.asyncio
    async def test_fans_out_when_multiple_waiting(self) -> None:
        """Multi-waiting shortcut fans out all waiting roles in parallel."""

        state = _state(member_status=_ledger({"analyst", "reviewer"}))
        result = await MustConsultAllMembers().try_shortcut(state)
        assert result is not None
        assert result.action_type == "delegate"
        roles = {s.target_role for s in list(result.delegations)}
        assert roles == {"analyst", "reviewer"}

    @pytest.mark.asyncio
    async def test_defers_when_all_settled(self) -> None:
        """may_respond 仍需要 LLM 生成 response_text，try_shortcut 不代劳。"""
        state = _state(member_status=_ledger({"a"}, {"a": "done"}))
        assert await MustConsultAllMembers().try_shortcut(state) is None

    @pytest.mark.asyncio
    async def test_defers_when_no_ledger(self) -> None:
        state = _state()  # member_status=None
        assert await MustConsultAllMembers().try_shortcut(state) is None


def test_gate_without_shortcut_is_not_supports_shortcut() -> None:
    """结构化实现 DecisionGate 但没有 try_shortcut 的 gate 不会被误判为支持快速路径。"""

    class _EnforceOnlyGate:
        async def enforce(self, state: AgentState, decision: Decision) -> Decision:
            return decision

    assert not isinstance(_EnforceOnlyGate(), SupportsShortcut)


class TestModularBrainTryShortcutShortCircuit:
    @pytest.mark.asyncio
    async def test_think_skips_reasoner_when_try_shortcut_fires(self) -> None:
        reasoner = MagicMock()
        reasoner.generate_thoughts = AsyncMock(
            side_effect=AssertionError("must not be called"),
        )
        brain = ModularBrain(
            reasoner=reasoner,
            decision_parser=SimpleDecisionParser(),
            critic=SimpleCritic(),
        )
        brain = ModularBrain(
            reasoner=brain.reasoner,
            decision_parser=brain.decision_parser,
            critic=brain.critic,
            evaluation_pipeline=brain.evaluation_pipeline,
            skill_router=brain.skill_router,
            decision_gate=MustConsultAllMembers(),
        )

        state = _state(member_status=_ledger({"analyst"}))
        decision = await brain.think(state)

        assert decision.action_type == "delegate"
        reasoner.generate_thoughts.assert_not_called()


# ── settle_delegation + retry ──


class TestSettleDelegation:
    @pytest.mark.asyncio
    async def test_marks_done_on_success(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(member_status=ledger)

        decision = _decision(
            "delegate",
            delegations=[DelegationSpec(target_role="analyst", subtask="analyze")],
        )
        obs = _obs(success=True)

        settle_delegation(state, decision.delegations[0], obs)

        assert _settlement(state) is not None
        assert _settlement(state).member_status.status["analyst"] == "done"

    @pytest.mark.asyncio
    async def test_marks_pending_on_first_execution_failure(self) -> None:
        """First execution failure stays PENDING (retry, not terminal)."""
        ledger = _ledger({"analyst"})
        state = _state(member_status=ledger)

        decision = _decision(
            "delegate",
            delegations=[DelegationSpec(target_role="analyst", subtask="analyze")],
        )
        obs = _obs(success=False, error="boom")

        settle_delegation(state, decision.delegations[0], obs)

        assert _settlement(state) is not None
        assert _settlement(state).member_status.status["analyst"] == "pending"
        assert _settlement(state).attempts["analyst"] == 1

    @pytest.mark.asyncio
    async def test_marks_failed_after_max_attempts(self) -> None:
        """Exceeding max_attempts → FAILED (terminal)."""
        ledger = _ledger({"analyst"})
        state = _state(member_status=ledger)
        assert _settlement(state) is not None
        _settlement(state).max_attempts = 2

        decision = _decision(
            "delegate",
            delegations=[DelegationSpec(target_role="analyst", subtask="analyze")],
        )
        obs = _obs(success=False, error="boom")

        settle_delegation(state, decision.delegations[0], obs)  # attempt 1 → pending
        assert _settlement(state).member_status.status["analyst"] == "pending"

        settle_delegation(state, decision.delegations[0], obs)  # attempt 2 → failed
        assert _settlement(state).member_status.status["analyst"] == "failed"
        assert _settlement(state).attempts["analyst"] == 2
        assert _settlement(state).member_status.all_settled() is True

    @pytest.mark.asyncio
    async def test_validation_failure_immediately_failed(self) -> None:
        """Validation-type failure → immediate FAILED (no retry)."""
        ledger = _ledger({"analyst"})
        state = _state(member_status=ledger)

        decision = _decision(
            "delegate",
            delegations=[DelegationSpec(target_role="analyst", subtask="analyze")],
        )
        obs = _obs(success=False, error="not found", failure_kind=FAILURE_KIND_VALIDATION)

        settle_delegation(state, decision.delegations[0], obs)

        assert _settlement(state).member_status.status["analyst"] == "failed"
        assert _settlement(state).member_status.all_settled() is True
        assert _settlement(state).attempts["analyst"] == 1

    @pytest.mark.asyncio
    async def test_noop_without_team_awareness(self) -> None:
        state = _state()  # no team awareness at all
        spec = DelegationSpec(target_role="analyst", subtask="analyze")
        settle_delegation(state, spec, _obs(success=True))

    @pytest.mark.asyncio
    async def test_noop_for_non_required_role(self) -> None:
        ledger = _ledger({"analyst"})
        state = _state(member_status=ledger)
        spec = DelegationSpec(target_role="someone_else", subtask="chore")
        settle_delegation(state, spec, _obs(success=True))
        assert _settlement(state).member_status.status["analyst"] == "pending"


# ── _next_role_status pure function ──


class TestNextRoleStatus:
    """Table-driven exhaustive test for the retry classification pure function."""

    @pytest.mark.parametrize(
        "success,failure_kind,attempts_after,max_attempts,expected",
        [
            # success → always DONE
            (True, "execution", 0, 3, "done"),
            (True, "validation", 0, 3, "done"),
            (True, "transient", 0, 3, "done"),
            # validation → always FAILED immediately
            (False, "validation", 0, 3, "failed"),
            (False, "validation", 1, 3, "failed"),
            (False, "validation", 2, 3, "failed"),
            # execution/transient → PENDING until max, then FAILED
            (False, "execution", 1, 3, "pending"),
            (False, "execution", 2, 3, "pending"),
            (False, "execution", 3, 3, "failed"),
            (False, "transient", 1, 3, "pending"),
            (False, "transient", 2, 3, "pending"),
            (False, "transient", 3, 3, "failed"),
            # default fallback kind (missing) → treated as execution
            (False, "unknown_kind", 1, 3, "pending"),
            (False, "unknown_kind", 3, 3, "failed"),
            # max_attempts = 1 → first failure is terminal
            (False, "execution", 1, 1, "failed"),
            (False, "transient", 1, 1, "failed"),
        ],
    )
    def test_classification(
        self,
        success: bool,
        failure_kind: str,
        attempts_after: int,
        max_attempts: int,
        expected: str,
    ) -> None:
        result = _next_role_status(
            success=success,
            failure_kind=failure_kind,
            attempts_after=attempts_after,
            max_attempts=max_attempts,
        )
        assert result == RoleStatus(expected)


# ── role_status_rules ──


class TestRoleStatusRules:
    @pytest.mark.parametrize(
        "status,terminal,success",
        [
            (RoleStatus.PENDING, False, False),
            (RoleStatus.IN_PROGRESS, False, False),
            (RoleStatus.DONE, True, True),
            (RoleStatus.FAILED, True, False),
        ],
    )
    def test_classification(self, status: RoleStatus, terminal: bool, success: bool) -> None:
        assert is_terminal_status(status) is terminal
        assert is_success_status(status) is success


# ── compute_required_action ──


class TestComputeRequiredAction:
    def test_must_delegate_when_waiting(self) -> None:
        ledger = InMemoryMemberStatus(
            role_order=("a", "b"), status={"a": "pending", "b": "pending"}
        )
        action = compute_required_action(ledger)
        assert action.kind == "must_delegate"
        assert action.target_role == "a"  # first in role_order

    def test_must_delegate_when_partial(self) -> None:
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "pending"})
        action = compute_required_action(ledger)
        assert action.kind == "must_delegate"
        assert action.target_role == "b"

    def test_may_respond_when_all_done(self) -> None:
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "done"})
        action = compute_required_action(ledger)
        assert action.kind == "may_respond"
        assert action.target_role is None

    def test_may_respond_when_all_settled_with_failures(self) -> None:
        ledger = _ledger({"a", "b"}, {"a": "done", "b": "failed"})
        action = compute_required_action(ledger)
        assert action.kind == "may_respond"
        assert action.target_role is None


# ── remaining_seconds / elapsed_seconds ──


class TestTimeUtilities:
    def test_remaining_seconds_future(self) -> None:
        now = utc_now()
        deadline = now + timedelta(seconds=30)
        assert abs(remaining_seconds(deadline, now=now) - 30.0) < 0.01

    def test_remaining_seconds_past(self) -> None:
        now = utc_now()
        deadline = now - timedelta(seconds=10)
        result = remaining_seconds(deadline, now=now)
        assert result < 0  # negative = already expired

    def test_remaining_seconds_zero(self) -> None:
        now = utc_now()
        assert abs(remaining_seconds(now, now=now)) < 0.001

    def test_elapsed_seconds(self) -> None:
        now = utc_now()
        started = now - timedelta(seconds=60)
        assert abs(elapsed_seconds(started, now=now) - 60.0) < 0.01

    def test_remaining_seconds_uses_utc_now_by_default(self) -> None:
        deadline = utc_now() + timedelta(seconds=5)
        result = remaining_seconds(deadline)
        assert 0 < result < 10  # roughly 5 seconds, with some tolerance
