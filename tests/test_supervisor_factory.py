"""Lead composition / closed-graph composition (ADR-0030)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from lca.contracts.enums import ActionType, DecisionGateName
from lca.contracts.team_coordination import LeadMandate, gate_name_for_mandate
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import SimpleReasoner, SupervisorReasoner
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer4_app.composer import TeamComposer
from lca.layer4_app.team_wiring import build_team_transport


def _raw_agent(role: str = "lead") -> CognitiveAgent:
    return TeamComposer().compose(
        role=role,
        goal="g",
        backstory="b",
        tools=[],
        llm=MockLLMAdapter(),
        max_steps=5,
    )


class TestLeadMandateMapping(unittest.TestCase):
    def test_board_maps_to_must_consult(self) -> None:
        self.assertEqual(
            gate_name_for_mandate(LeadMandate.BOARD),
            DecisionGateName.MUST_CONSULT_ALL,
        )

    def test_routing_and_consult_map_to_none(self) -> None:
        self.assertEqual(gate_name_for_mandate(LeadMandate.ROUTING), DecisionGateName.NONE)
        self.assertEqual(gate_name_for_mandate(LeadMandate.CONSULT), DecisionGateName.NONE)


class TestComposeAsLead(unittest.IsolatedAsyncioTestCase):
    async def test_new_instance_with_lead_reasoner_and_gate(self) -> None:
        asm = TeamComposer()
        raw = _raw_agent()
        member = _raw_agent("worker")
        transport = build_team_transport([member])
        lead = asm.compose_as_lead(raw, transport=transport, mandate=LeadMandate.BOARD)
        self.assertIsNot(lead, raw)
        brain = lead.runtime.brain  # type: ignore[attr-defined]
        self.assertIsInstance(brain, ModularBrain)
        self.assertIsInstance(brain.reasoner, SupervisorReasoner)
        self.assertIsInstance(brain._decision_gate, MustConsultAllMembers)
        body = getattr(lead.runtime, "body", None)
        inner = getattr(body, "_inner", body)
        registry = getattr(inner, "action_registry", None)
        self.assertIsNotNone(registry)
        self.assertIsNotNone(registry.get(ActionType.DELEGATE))

    async def test_routing_mandate_has_no_gate(self) -> None:
        asm = TeamComposer()
        raw = _raw_agent()
        member = _raw_agent("worker")
        transport = build_team_transport([member])
        lead = asm.compose_as_lead(raw, transport=transport, mandate=LeadMandate.ROUTING)
        brain = lead.runtime.brain  # type: ignore[attr-defined]
        self.assertIsInstance(brain.reasoner, SupervisorReasoner)
        self.assertIsNone(brain._decision_gate)

    async def test_no_bind_or_install_apis(self) -> None:
        body = (
            TeamComposer()
            .compose(role="x", goal="g", backstory="b", tools=[], llm=MockLLMAdapter())
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


class TestComposeTeamClosedGraph(unittest.IsolatedAsyncioTestCase):
    async def test_lead_board_team_has_closed_lead(self) -> None:
        asm = TeamComposer()
        llm = MockLLMAdapter()
        workers = [
            asm.compose(role=r, goal="g", backstory="b", tools=[], llm=llm, max_steps=3)
            for r in ("a", "b")
        ]
        lead = asm.compose(role="lead", goal="g", backstory="b", tools=[], llm=llm, max_steps=5)
        team = asm.compose_team(
            members=workers,
            lead=(lead, LeadMandate.BOARD),
        )
        self.assertIsNotNone(team.lead)
        self.assertIsInstance(team.lead.runtime.brain.reasoner, SupervisorReasoner)  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
