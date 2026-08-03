"""SupervisorFactory / closed-graph composition (ADR-0029)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from lca.contracts.enums import ActionType, DecisionGateName, TeamProcess
from lca.contracts.supervisor_mode import SupervisorMode, decision_gate_name_for_mode
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import SimpleReasoner, SupervisorReasoner
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer4_app.assembly import Assembly
from lca.layer4_app.team_wiring import build_team_transport


def _raw_agent(role: str = "lead") -> CognitiveAgent:
    return Assembly().assemble_agent(
        role=role,
        goal="g",
        backstory="b",
        tools=[],
        llm=MockLLMAdapter(),
        max_steps=5,
    )


class TestSupervisorModeMapping(unittest.TestCase):
    def test_board_maps_to_must_consult(self) -> None:
        self.assertEqual(
            decision_gate_name_for_mode(SupervisorMode.BOARD),
            DecisionGateName.MUST_CONSULT_ALL,
        )

    def test_routing_and_consult_map_to_none(self) -> None:
        self.assertEqual(decision_gate_name_for_mode(SupervisorMode.ROUTING), DecisionGateName.NONE)
        self.assertEqual(
            decision_gate_name_for_mode(SupervisorMode.CONSULTATION), DecisionGateName.NONE
        )


class TestRecomposeAsSupervisor(unittest.IsolatedAsyncioTestCase):
    async def test_new_instance_with_supervisor_reasoner_and_gate(self) -> None:
        asm = Assembly()
        raw = _raw_agent()
        member = _raw_agent("worker")
        transport = build_team_transport([member])
        sup = asm.recompose_as_supervisor(raw, transport=transport, mode=SupervisorMode.BOARD)
        self.assertIsNot(sup, raw)
        brain = sup.runtime.brain  # type: ignore[attr-defined]
        self.assertIsInstance(brain, ModularBrain)
        self.assertIsInstance(brain.reasoner, SupervisorReasoner)
        self.assertIsInstance(brain._decision_gate, MustConsultAllMembers)
        # DELEGATE registered for supervisor scope
        body = getattr(sup.runtime, "body", None)
        inner = getattr(body, "_inner", body)
        registry = getattr(inner, "action_registry", None)
        self.assertIsNotNone(registry)
        self.assertIsNotNone(registry.get(ActionType.DELEGATE))

    async def test_routing_mode_has_no_gate(self) -> None:
        asm = Assembly()
        raw = _raw_agent()
        member = _raw_agent("worker")
        transport = build_team_transport([member])
        sup = asm.recompose_as_supervisor(raw, transport=transport, mode=SupervisorMode.ROUTING)
        brain = sup.runtime.brain  # type: ignore[attr-defined]
        self.assertIsInstance(brain.reasoner, SupervisorReasoner)
        self.assertIsNone(brain._decision_gate)

    async def test_no_bind_or_install_apis(self) -> None:
        body = (
            Assembly()
            .assemble_agent(role="x", goal="g", backstory="b", tools=[], llm=MockLLMAdapter())
            .runtime.body
        )  # type: ignore[attr-defined]
        inner = getattr(body, "_inner", body)
        self.assertFalse(hasattr(inner, "bind_channel"))
        brain = ModularBrain(
            reasoner=MagicMock(spec=SimpleReasoner),
            decision_parser=MagicMock(),
            critic=MagicMock(),
        )
        self.assertFalse(hasattr(brain, "install_decision_gate"))


class TestAssembleTeamClosedGraph(unittest.IsolatedAsyncioTestCase):
    async def test_hierarchical_board_run_completes(self) -> None:
        asm = Assembly()
        llm = MockLLMAdapter()
        workers = [
            asm.assemble_agent(role=r, goal="g", backstory="b", tools=[], llm=llm, max_steps=3)
            for r in ("a", "b")
        ]
        lead = asm.assemble_agent(
            role="lead", goal="g", backstory="b", tools=[], llm=llm, max_steps=5
        )
        team = asm.assemble_team(
            members=workers,
            process=TeamProcess.HIERARCHICAL,
            supervisor=lead,
            supervisor_mode=SupervisorMode.BOARD,
        )
        self.assertIsNotNone(team.supervisor)
        self.assertIsInstance(team.supervisor.runtime.brain.reasoner, SupervisorReasoner)  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
