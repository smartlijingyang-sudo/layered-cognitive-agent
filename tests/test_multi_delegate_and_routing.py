"""Multi-delegate fan-out, routing plane, and peer swarm."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from lca.contracts.decision import Decision, DelegationSpec, Observation
from lca.contracts.enums import DecisionGateName, RoleStatus, TeamProcess
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.orchestration_taxonomy import (
    ROUTING_SETTLEMENT_GATE_ERROR,
    SupervisorPlane,
)
from lca.contracts.protocols import TeamContext
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile, TeamConfig, ToolPermissionManifest
from lca.contracts.routing import RoutingState, assert_routing_field_whitelist
from lca.contracts.state import AgentState, Budget
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.brain.decision_gates.must_consult_all import MustConsultAllMembers
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.member_status import InMemoryMemberStatus
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer3_agent.orchestration_strategies import (
    HierarchicalStrategy,
    SwarmStrategy,
)
from lca.layer3_agent.team_orchestrator import TeamOrchestrator
from lca.layer4_app.assembly import Assembly
from lca.layer4_app.defaults import build_default_registries
from tests.support.team_context import team_context_with_transport


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
            SimpleToolRegistry(), _noop_executor(), transport_registry=_make_registry(transport)
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
        from lca.contracts.consultation import ConsultationState

        state = AgentState(
            trace_id="t",
            task="t",
            budget=Budget(),
            consultation=ConsultationState(member_status=board, teammates=[]),
        )
        obs = await body.act(decision, state)
        self.assertTrue(obs.success)
        assert isinstance(obs.payload, dict)
        self.assertIn("ra", obs.payload)
        self.assertEqual(state.consultation.member_status.status["ra"], RoleStatus.DONE)
        self.assertEqual(state.consultation.member_status.status["rb"], RoleStatus.DONE)


class TestMustConsultMultiShortcut(unittest.IsolatedAsyncioTestCase):
    async def test_shortcut_fans_out_all_waiting(self) -> None:
        board = InMemoryMemberStatus(role_order=("a", "b", "c"))
        from lca.contracts.consultation import ConsultationState

        state = AgentState(
            trace_id="t",
            task="evaluate",
            budget=Budget(),
            consultation=ConsultationState(member_status=board, teammates=[]),
        )
        gate = MustConsultAllMembers()
        d = await gate.try_shortcut(state)
        assert d is not None
        specs = list(d.delegations)
        self.assertEqual({s.target_role for s in specs}, {"a", "b", "c"})


class TestRoutingPlane(unittest.IsolatedAsyncioTestCase):
    def test_routing_whitelist(self) -> None:
        assert_routing_field_whitelist()

    async def test_routing_rejects_settlement_gate(self) -> None:
        reg = build_default_registries()
        profile = RoleProfile(
            role="lead",
            goal="g",
            backstory="b",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        rt = MagicMock()
        rt.brain = MagicMock()
        rt.brain.reasoner = MagicMock()
        from lca.layer1_cognitive.brain.reasoner import SimpleReasoner

        rt.brain.reasoner = SimpleReasoner(
            MagicMock(),
            profile,
            "t",
            templates={
                "react_prompt": "r",
                "hierarchical_prompt": "h {teammates} {member_status_text}",
                "routing_prompt": "rt {teammates} {assigned_roles_text} {notes}",
            },
        )
        rt.body = MagicMock()
        rt.body.bind_channel = MagicMock()
        rt.memory = MagicMock()
        sup = CognitiveAgent(rt, profile)
        member = CognitiveAgent(MagicMock(), profile)
        config = TeamConfig(
            process=TeamProcess.HIERARCHICAL,
            supervisor_plane=SupervisorPlane.ROUTING,
            decision_gate=DecisionGateName.MUST_CONSULT_ALL,
        )
        with self.assertRaises(ValueError) as orchestrator_err:
            TeamOrchestrator([member], config, registries=reg, supervisor=sup)
        self.assertEqual(str(orchestrator_err.exception), ROUTING_SETTLEMENT_GATE_ERROR)

        assembly = Assembly(registries=reg)
        with self.assertRaises(ValueError) as assembly_err:
            assembly.assemble_team(
                members=[member],
                process=TeamProcess.HIERARCHICAL,
                supervisor=sup,
                supervisor_plane=SupervisorPlane.ROUTING,
                decision_gate=DecisionGateName.MUST_CONSULT_ALL,
            )
        self.assertEqual(str(assembly_err.exception), ROUTING_SETTLEMENT_GATE_ERROR)
        self.assertEqual(str(orchestrator_err.exception), str(assembly_err.exception))

    async def test_hierarchical_routing_injects_routing_state(self) -> None:
        strategy = HierarchicalStrategy()
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
        ctx = TeamContext(
            members=[],
            supervisor=sup,
            teammates=[profile],
            config=TeamConfig(
                process=TeamProcess.HIERARCHICAL,
                supervisor_plane=SupervisorPlane.ROUTING,
            ),
        )
        result = await strategy.run(ctx, "obj")
        self.assertEqual(result.output, "ok")
        self.assertIsNotNone(captured[0])
        self.assertIsInstance(captured[0].routing, RoutingState)
        self.assertIsNone(captured[0].consultation)


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
        strategy = SwarmStrategy(max_rounds=1)
        result = await strategy.run(team_context_with_transport([a, b]), "task")
        self.assertEqual(result.output, "done")
        a.run.assert_awaited_once()
        b.run.assert_awaited_once()
