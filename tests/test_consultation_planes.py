"""ADR-0049：咨询资源平面 + 证据平面 + harvest + 解析防腐 全覆盖。"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock

from lca.contracts.atoms.enums import RoleStatus
from lca.contracts.atoms.semantic_keys import (
    COMPLETION_PARTIAL,
    FAILURE_KIND,
    FAILURE_KIND_TRANSIENT,
    OBS_COMPLETION_QUALITY,
)
from lca.contracts.models.core.budget import (
    DEFAULT_DELEGATION_TIMEOUT_S,
    resolve_delegation_timeout_s,
)
from lca.contracts.models.core.decision import Decision, DelegationSpec, Observation
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.consultation import (
    ConsultationDisposition,
    ConsultationOutcome,
    SynthesisMethod,
    usable_outcomes,
)
from lca.contracts.models.team.partial_buffer import (
    append_run_partial,
    begin_partial_buffer,
    drain_run_partial,
    reset_partial_buffer,
)
from lca.contracts.models.team.team_awareness import ConsultDuty, TeamAwareness
from lca.contracts.protocols.spec import DEFAULT_DELEGATE_MAX_ATTEMPTS
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer1_cognitive.body.action_handlers import resolve_spec_timeout_s
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.brain.decision_gates.must_consult_all import MustConsultAllMembers
from lca.layer1_cognitive.member_status import (
    InMemoryMemberStatus,
    classify_synthesis,
    compute_required_action_from_duty,
    record_delegation_return,
)
from lca.layer1_cognitive.member_status.tracking import duty_consult
from tests.support.action_authority import build_test_body


def _noop_executor() -> MagicMock:
    return MagicMock()


def _registry(transport: InternalTransport) -> TransportRegistry:
    reg = TransportRegistry()
    reg.register(transport)
    return reg


def _duty_state(
    roles: tuple[str, ...] = ("a", "b"),
    *,
    max_attempts: int = DEFAULT_DELEGATE_MAX_ATTEMPTS,
    wall: int | None = 300,
) -> AgentState:
    board = InMemoryMemberStatus(role_order=roles)
    return AgentState(
        trace_id="t",
        task="信贷办理业务流程是怎么样的",
        budget=Budget(max_wall_clock_seconds=wall),
        team_awareness=TeamAwareness(
            consult_duty=ConsultDuty(
                member_status=board,
                max_attempts=max_attempts,
                min_usable_partial_chars=20,
            )
        ),
    )


class TestResourcePlane(unittest.TestCase):
    def test_default_delegation_timeout_is_300(self) -> None:
        self.assertEqual(DEFAULT_DELEGATION_TIMEOUT_S, 300.0)

    def test_resolve_prefers_explicit(self) -> None:
        self.assertEqual(
            resolve_delegation_timeout_s(explicit_timeout_s=12.0, run_wall_clock_remaining_s=5.0),
            12.0,
        )

    def test_resolve_caps_by_run_budget(self) -> None:
        self.assertEqual(
            resolve_delegation_timeout_s(run_wall_clock_remaining_s=40.0),
            40.0,
        )

    def test_body_uses_spec_timeout_not_private_30(self) -> None:
        state = _duty_state()
        spec = DelegationSpec(subtask="x", target_role="a", timeout_s=77.0)
        self.assertEqual(resolve_spec_timeout_s(spec, state), 77.0)

    def test_body_defaults_to_300_when_no_spec_timeout(self) -> None:
        state = _duty_state(wall=None)  # 无墙钟上限 → 纯默认 300
        spec = DelegationSpec(subtask="x", target_role="a")
        self.assertEqual(resolve_spec_timeout_s(spec, state), DEFAULT_DELEGATION_TIMEOUT_S)

    def test_body_caps_timeout_by_remaining_wall_clock(self) -> None:
        state = _duty_state(wall=300)
        spec = DelegationSpec(subtask="x", target_role="a")
        timeout = resolve_spec_timeout_s(spec, state)
        self.assertLessEqual(timeout, DEFAULT_DELEGATION_TIMEOUT_S)
        self.assertGreater(timeout, 290.0)

    def test_no_private_30_constant_in_action_handlers(self) -> None:
        from pathlib import Path

        src = Path("lca/layer1_cognitive/body/action_handlers.py").read_text(encoding="utf-8")
        self.assertNotIn("_DEFAULT_DELEGATE_TIMEOUT_S", src)
        self.assertNotIn("= 30.0", src)


class TestPartialBuffer(unittest.TestCase):
    def test_append_and_drain(self) -> None:
        token = begin_partial_buffer()
        try:
            append_run_partial("hello ")
            append_run_partial("world")
            self.assertEqual(drain_run_partial(), "hello world")
            self.assertEqual(drain_run_partial(), "")
        finally:
            reset_partial_buffer(token)


class TestEvidenceAndPolicy(unittest.TestCase):
    def test_usable_partial_marks_done_partial_no_retry(self) -> None:
        state = _duty_state(roles=("architect",), max_attempts=3)
        duty = duty_consult(state)
        assert duty is not None
        obs = Observation(
            observation_id="o1",
            success=False,
            payload="这是一段足够长的部分证据，用于覆盖信贷流程视角。",
            error="delegate 超时",
            extra={
                FAILURE_KIND: FAILURE_KIND_TRANSIENT,
                OBS_COMPLETION_QUALITY: COMPLETION_PARTIAL,
            },
        )
        record_delegation_return(state, DelegationSpec(subtask="s", target_role="architect"), obs)
        self.assertEqual(duty.member_status.status["architect"], RoleStatus.DONE_PARTIAL)
        nxt = compute_required_action_from_duty(duty, state)
        self.assertEqual(nxt.kind, "may_respond")
        self.assertEqual(nxt.synthesis_method, SynthesisMethod.PARTIAL)
        self.assertEqual(len(usable_outcomes(duty.outcomes)), 1)

    def test_empty_timeout_retries_then_fails(self) -> None:
        state = _duty_state(roles=("a",), max_attempts=2)
        duty = duty_consult(state)
        assert duty is not None
        empty = Observation(
            observation_id="o",
            success=False,
            payload=None,
            error="delegate 超时",
            extra={FAILURE_KIND: FAILURE_KIND_TRANSIENT, OBS_COMPLETION_QUALITY: "empty"},
        )
        record_delegation_return(state, DelegationSpec(subtask="s", target_role="a"), empty)
        self.assertEqual(duty.member_status.status["a"], RoleStatus.PENDING)
        nxt = compute_required_action_from_duty(duty, state)
        self.assertEqual(nxt.kind, "must_consult")
        self.assertEqual(nxt.target_roles, ("a",))

        record_delegation_return(state, DelegationSpec(subtask="s", target_role="a"), empty)
        self.assertEqual(duty.member_status.status["a"], RoleStatus.FAILED)
        nxt2 = compute_required_action_from_duty(duty, state)
        self.assertEqual(nxt2.kind, "may_respond")
        self.assertEqual(nxt2.synthesis_method, SynthesisMethod.SOLO_FALLBACK)

    def test_classify_full(self) -> None:
        board = InMemoryMemberStatus(role_order=("a",))
        board = board.mark("a", RoleStatus.DONE)
        outcomes = [
            ConsultationOutcome(
                outcome_id="1",
                role="a",
                attempt=1,
                disposition=ConsultationDisposition.COMPLETED,
                evidence="full text",
                usable=True,
                failure_kind=None,
                task_id=None,
                delegation_id=None,
                step=0,
                returned_at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
            )
        ]
        self.assertEqual(classify_synthesis(board, outcomes), SynthesisMethod.FULL)


class TestGateBudget(unittest.IsolatedAsyncioTestCase):
    async def test_shortcut_attaches_timeout_s(self) -> None:
        state = _duty_state(roles=("a", "b"), wall=300)
        gate = MustConsultAllMembers()
        d = await gate.try_shortcut(state)
        assert d is not None
        self.assertEqual(d.action_type, "delegate")
        self.assertEqual(len(d.delegations), 2)
        for spec in d.delegations:
            self.assertIsNotNone(spec.timeout_s)
            assert spec.timeout_s is not None
            self.assertGreaterEqual(spec.timeout_s, 299.0)


class TestTransportHarvest(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_returns_partial_observation(self) -> None:
        transport = InternalTransport()

        async def slow_partial(subtask: str) -> Observation:
            await asyncio.sleep(0.05)
            # 模拟被 cancel 前返回 partial（handler 路径）
            await asyncio.sleep(1.0)
            return Observation(observation_id="late", success=True, payload="too late")

        async def cooperative(subtask: str) -> Observation:
            try:
                await asyncio.sleep(5.0)
                return Observation(observation_id="x", success=True, payload="done")
            except asyncio.CancelledError:
                return Observation(
                    observation_id="partial",
                    success=False,
                    payload="## 部分流程\n贷前-贷中-贷后",
                    error="canceled",
                    extra={
                        FAILURE_KIND: FAILURE_KIND_TRANSIENT,
                        OBS_COMPLETION_QUALITY: COMPLETION_PARTIAL,
                    },
                )

        transport.register_agent("worker", cooperative)
        task_id = await transport.send_task("worker", "task", [])
        obs = await transport.wait_result(task_id, timeout_s=0.05)
        self.assertFalse(obs.success)
        self.assertIn("贷前", str(obs.payload or ""))
        self.assertEqual(obs.extra.get(OBS_COMPLETION_QUALITY), COMPLETION_PARTIAL)

    async def test_body_records_partial_outcome(self) -> None:
        transport = InternalTransport()

        async def cooperative(subtask: str) -> Observation:
            try:
                await asyncio.sleep(5.0)
                return Observation(observation_id="x", success=True, payload="done")
            except asyncio.CancelledError:
                return Observation(
                    observation_id="p",
                    success=False,
                    payload="部分证据正文内容足够长了吧要超过二十字符",
                    error="delegate 超时",
                    extra={
                        FAILURE_KIND: FAILURE_KIND_TRANSIENT,
                        OBS_COMPLETION_QUALITY: COMPLETION_PARTIAL,
                    },
                )

        transport.register_agent("a", cooperative)
        body = build_test_body(
            SimpleToolRegistry(),
            _noop_executor(),
            transport=_registry(transport),
        )
        state = _duty_state(roles=("a",), max_attempts=1)
        decision = Decision(
            decision_id="d",
            action_type="delegate",
            rationale="t",
            confidence=1.0,
            delegations=[DelegationSpec(subtask="s", target_role="a", timeout_s=0.05)],
        )
        obs = await body.act(decision, state)
        self.assertFalse(obs.success)
        duty = duty_consult(state)
        assert duty is not None
        self.assertEqual(duty.member_status.status["a"], RoleStatus.DONE_PARTIAL)
        self.assertTrue(duty.outcomes[0].usable)


if __name__ == "__main__":
    unittest.main()
