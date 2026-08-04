"""Lead composition / closed-graph composition (ADR-0030 / ADR-0033 / ADR-0035)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from lca.contracts.agent_spec import AgentSpec, LeadSpec
from lca.contracts.enums import ActionType, DecisionGateName
from lca.contracts.team_coordination import LeadMandate, gate_name_for_mandate
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import PromptReasoner
from lca.layer4_app.composer import TeamComposer
from lca.layer4_app.team_wiring import build_team_transport
from tests.support.agent_specs import make_spec


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
    async def test_new_instance_with_gate(self) -> None:
        """ADR-0035：lead 不做 reasoner 升级——gate 是唯一按 mandate 展开的组合差异。"""
        asm = TeamComposer()
        member_spec = make_spec("worker", MockLLMAdapter())
        member = asm.compose(member_spec)
        transport = build_team_transport([member])
        lead = asm.compose_as_lead(
            make_spec("lead", MockLLMAdapter()),
            transport=transport,
            mandate=LeadMandate.BOARD,
        )
        brain = lead.runtime.brain  # type: ignore[attr-defined]
        self.assertIsInstance(brain, ModularBrain)
        self.assertIsInstance(brain.reasoner, PromptReasoner)
        self.assertIsInstance(brain._decision_gate, MustConsultAllMembers)
        body = getattr(lead.runtime, "body", None)
        inner = getattr(body, "_inner", body)
        registry = getattr(inner, "action_registry", None)
        self.assertIsNotNone(registry)
        self.assertIsNotNone(registry.get(ActionType.DELEGATE))

    async def test_routing_mandate_has_no_gate(self) -> None:
        asm = TeamComposer()
        member = asm.compose(make_spec("worker", MockLLMAdapter()))
        transport = build_team_transport([member])
        lead = asm.compose_as_lead(
            make_spec("lead", MockLLMAdapter()),
            transport=transport,
            mandate=LeadMandate.ROUTING,
        )
        brain = lead.runtime.brain  # type: ignore[attr-defined]
        self.assertIsInstance(brain.reasoner, PromptReasoner)
        self.assertIsNone(brain._decision_gate)

    async def test_no_bind_or_install_apis(self) -> None:
        body = TeamComposer().compose(make_spec("x", MockLLMAdapter())).runtime.body  # type: ignore[attr-defined]
        inner = getattr(body, "_inner", body)
        self.assertFalse(hasattr(inner, "bind_channel"))
        brain = ModularBrain(
            reasoner=MagicMock(spec=PromptReasoner),
            decision_parser=MagicMock(),
            critic=MagicMock(),
        )
        self.assertFalse(hasattr(brain, "install_decision_gate"))


class TestComposeTeamClosedGraph(unittest.IsolatedAsyncioTestCase):
    async def test_lead_board_team_has_closed_lead(self) -> None:
        asm = TeamComposer()
        llm = MockLLMAdapter()
        team = asm.compose_team(
            members=[make_spec(role, llm, max_steps=3) for role in ("a", "b")],
            lead=LeadSpec(make_spec("lead", llm), LeadMandate.BOARD),
        )
        self.assertIsNotNone(team.lead)
        self.assertIsInstance(team.lead.runtime.brain.reasoner, PromptReasoner)  # type: ignore[attr-defined]

    async def test_compose_rejects_missing_spec_shape(self) -> None:
        """compose 只接受 AgentSpec —— 成品 agent 不再是组合输入。"""
        asm = TeamComposer()
        composed = asm.compose(make_spec("x", MockLLMAdapter()))
        with self.assertRaises(AttributeError):
            asm.compose(composed)  # type: ignore[arg-type]


class TestSpecIsCompositionSource(unittest.TestCase):
    def test_spec_is_frozen_value_object(self) -> None:
        spec = make_spec("x", MockLLMAdapter())
        self.assertIsInstance(spec, AgentSpec)
        with self.assertRaises(AttributeError):
            spec.max_steps = 99  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
