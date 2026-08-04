"""Multi-delegate fan-out, routing plane, and peer swarm."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from lca.contracts.agent_spec import DEFAULT_DELEGATE_MAX_ATTEMPTS
from lca.contracts.decision import Decision, DelegationSpec, Observation
from lca.contracts.enums import ActionScope, DecisionGateName, RoleStatus
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.state import AgentState, Budget
from lca.contracts.team_awareness import Settlement, TeamAwareness
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.brain.decision_gates.must_consult_all import MustConsultAllMembers
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.member_status import InMemoryMemberStatus
from lca.layer3_agent.orchestration_strategies import (
    LeadStrategy,
    SwarmStrategy,
)
from tests.support.team_stage import stage_with_invoker


def _noop_executor() -> MagicMock:
    return MagicMock()


def _make_registry(transport: InternalTransport) -> TransportRegistry:
    reg = TransportRegistry()
    reg.register(transport)
    return reg


class TestMultiDelegateParse(unittest.TestCase):
    def test_parser_multi_targets(self) -> None:
        raw = """
        {
          "action_type": "delegate",
          "rationale": "fan-out",
          "confidence": 0.9,
          "delegations": [
            {"target_role": "a", "subtask": "ta"},
            {"target_role": "b", "subtask": "tb"}
          ]
        }
        """
        d = SimpleDecisionParser().parse(raw, AgentState(trace_id="t", task="x", budget=Budget()))
        specs = list(d.delegations)
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0].target_role, "a")
        self.assertEqual(d.delegations[0].target_role, "a")


class TestMultiDelegateBody(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_delegate(self) -> None:
        transport = InternalTransport()
        seen: list[str] = []

        async def _ha(sub: str) -> Observation:
            await asyncio.sleep(0.05)
            seen.append("a")
            return Observation(observation_id="a", success=True, payload=f"A:{sub}")

        async def _hb(sub: str) -> Observation:
            await asyncio.sleep(0.05)
            seen.append("b")
            return Observation(observation_id="b", success=True, payload=f"B:{sub}")

        transport.register_agent("ra", _ha)
        transport.register_agent("rb", _hb)
        body = SimpleBody(
            SimpleToolRegistry(),
            _noop_executor(),
            transport_registry=_make_registry(transport),
            action_scope=ActionScope.LEAD,
        )
        decision = Decision(
            decision_id="d1",
            action_type="delegate",
            rationale="multi",
            confidence=1.0,
            delegations=[
                DelegationSpec(subtask="1", target_role="ra"),
                DelegationSpec(subtask="2", target_role="rb"),
            ],
        )
        board = InMemoryMemberStatus(role_order=("ra", "rb"))
        state = AgentState(
            trace_id="t",
            task="t",
            budget=Budget(),
            team_awareness=TeamAwareness(
                settlement=Settlement(
                    member_status=board, max_attempts=DEFAULT_DELEGATE_MAX_ATTEMPTS
                )
            ),
        )
        obs = await body.act(decision, state)
        self.assertTrue(obs.success)
        assert isinstance(obs.payload, dict)
        self.assertIn("ra", obs.payload)
        assert state.team_awareness is not None
        assert state.team_awareness.settlement is not None
        self.assertEqual(
            state.team_awareness.settlement.member_status.status["ra"], RoleStatus.DONE
        )
        self.assertEqual(
            state.team_awareness.settlement.member_status.status["rb"], RoleStatus.DONE
        )


class TestMustConsultMultiShortcut(unittest.IsolatedAsyncioTestCase):
    async def test_shortcut_fans_out_all_waiting(self) -> None:
        board = InMemoryMemberStatus(role_order=("a", "b", "c"))
        state = AgentState(
            trace_id="t",
            task="evaluate",
            budget=Budget(),
            team_awareness=TeamAwareness(
                settlement=Settlement(
                    member_status=board, max_attempts=DEFAULT_DELEGATE_MAX_ATTEMPTS
                )
            ),
        )
        gate = MustConsultAllMembers()
        d = await gate.try_shortcut(state)
        assert d is not None
        specs = list(d.delegations)
        self.assertEqual({s.target_role for s in specs}, {"a", "b", "c"})


class TestRoutingPlane(unittest.IsolatedAsyncioTestCase):
    async def test_routing_mode_never_maps_to_settlement_gate(self) -> None:
        from lca.contracts.team_coordination import LeadMandate, gate_name_for_mandate

        self.assertEqual(gate_name_for_mandate(LeadMandate.ROUTING), DecisionGateName.NONE)
        # Illegal plane×gate product is not representable via LeadMandate.
        self.assertNotEqual(
            gate_name_for_mandate(LeadMandate.ROUTING),
            DecisionGateName.MUST_CONSULT_ALL,
        )

    async def test_routing_lead_injects_awareness_without_settlement(self) -> None:
        sup = MagicMock()
        captured: list = []

        async def _run(task: str, ctx=None) -> Result:
            captured.append(ctx)
            return Result(
                trace_id="t",
                status=TaskStatus.COMPLETED,
                final_state_ref="m",
                total_steps=1,
                budget_used=Budget(),
                output="ok",
            )

        sup.run = AsyncMock(side_effect=_run)
        profile = RoleProfile(
            role="m",
            goal="g",
            backstory="b",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        strategy = LeadStrategy(
            lead=sup,
            roster=(profile,),
            board=None,
            delegate_max_attempts=DEFAULT_DELEGATE_MAX_ATTEMPTS,
        )
        result = await strategy.run("obj")
        self.assertEqual(result.output, "ok")
        self.assertIsNotNone(captured[0])
        awareness = captured[0].team_awareness
        self.assertIsInstance(awareness, TeamAwareness)
        self.assertIsNone(awareness.settlement)
        self.assertEqual([p.role for p in awareness.teammates], ["m"])


class TestPeerSwarm(unittest.IsolatedAsyncioTestCase):
    async def test_swarm_stops_on_first_success_with_output(self) -> None:
        a = MagicMock()
        a.role_profile = MagicMock()
        a.role_profile.role = "a"
        a.run = AsyncMock(
            return_value=Result(
                trace_id="1",
                status=TaskStatus.FAILED,
                final_state_ref="m",
                total_steps=1,
                budget_used=Budget(),
                output="",
            )
        )
        b = MagicMock()
        b.role_profile = MagicMock()
        b.role_profile.role = "b"
        b.run = AsyncMock(
            return_value=Result(
                trace_id="2",
                status=TaskStatus.COMPLETED,
                final_state_ref="m",
                total_steps=2,
                budget_used=Budget(),
                output="done",
            )
        )
        strategy = SwarmStrategy(stage_with_invoker([a, b]), max_rounds=1)
        result = await strategy.run("task")
        self.assertEqual(result.output, "done")
        a.run.assert_awaited_once()
        b.run.assert_awaited_once()
