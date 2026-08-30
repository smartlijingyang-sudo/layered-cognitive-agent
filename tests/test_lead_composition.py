"""Lead composition / closed-graph composition (ADR-0030 / ADR-0033 / ADR-0035)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from lca.contracts.atoms.enums import ActionType, DecisionGateName
from lca.contracts.models.team.team_coordination import LeadMandate, gate_name_for_mandate
from lca.contracts.protocols.spec import AgentSpec, LeadSpec
from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import PromptReasoner
from lca.layer2_runtime.reducer import DefaultReducer
from lca.layer4_app.api import ensure_default_ctx
from lca.layer4_app.spawn import spawn_agent, spawn_lead, spawn_team
from lca.plugins.composer.team_transport import build_team_transport
from lca.plugins.providers.decision_classifier import DefaultDecisionClassifier
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
    async def asyncSetUp(self) -> None:
        await ensure_default_ctx()

    async def test_new_instance_with_gate(self) -> None:
        """ADR-0035：lead 不做 reasoner 升级——gate 是唯一按 mandate 展开的组合差异。"""
        member = spawn_agent(make_spec("worker", MockLLMAdapter()))
        transport = build_team_transport([member])
        lead = spawn_lead(
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
        member = spawn_agent(make_spec("worker", MockLLMAdapter()))
        transport = build_team_transport([member])
        lead = spawn_lead(
            make_spec("lead", MockLLMAdapter()),
            transport=transport,
            mandate=LeadMandate.ROUTING,
        )
        brain = lead.runtime.brain  # type: ignore[attr-defined]
        self.assertIsInstance(brain.reasoner, PromptReasoner)
        self.assertIsNone(brain._decision_gate)

    async def test_explicit_team_transport_replaces_inherited_protocol(self) -> None:
        member = spawn_agent(make_spec("worker", MockLLMAdapter()))
        team_transport = build_team_transport([member])
        lead = spawn_lead(
            make_spec("lead", MockLLMAdapter()),
            transport=team_transport,
            mandate=LeadMandate.ROUTING,
        )

        body = lead.runtime.body  # type: ignore[attr-defined]
        inner = getattr(body, "_inner", body)
        self.assertIs(inner.transport_registry.resolve("internal"), team_transport)

    async def test_no_bind_or_install_apis(self) -> None:
        body = spawn_agent(make_spec("x", MockLLMAdapter())).runtime.body  # type: ignore[attr-defined]
        inner = getattr(body, "_inner", body)
        self.assertFalse(hasattr(inner, "bind_channel"))
        brain = ModularBrain(
            reasoner=MagicMock(spec=PromptReasoner),
            reducer=DefaultReducer(),
            classifier=DefaultDecisionClassifier(),
            critic=MagicMock(),
        )
        self.assertFalse(hasattr(brain, "install_decision_gate"))


class TestComposeTeamClosedGraph(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await ensure_default_ctx()

    async def test_lead_board_team_has_closed_lead(self) -> None:
        llm = MockLLMAdapter()
        team = spawn_team(
            members=[make_spec(role, llm, max_steps=3) for role in ("a", "b")],
            lead=LeadSpec(make_spec("lead", llm), LeadMandate.BOARD),
        )
        self.assertIsNotNone(team.lead)
        self.assertIsInstance(team.lead.runtime.brain.reasoner, PromptReasoner)  # type: ignore[attr-defined]

    async def test_spawn_rejects_missing_spec_shape(self) -> None:
        """spawn_agent 只接受 AgentSpec —— 成品 agent 不再是组合输入。"""
        composed = spawn_agent(make_spec("x", MockLLMAdapter()))
        with self.assertRaises(AttributeError):
            spawn_agent(composed)  # type: ignore[arg-type]


class TestSpecIsCompositionSource(unittest.TestCase):
    def test_spec_is_frozen_value_object(self) -> None:
        spec = make_spec("x", MockLLMAdapter())
        self.assertIsInstance(spec, AgentSpec)
        with self.assertRaises(AttributeError):
            spec.max_steps = 99  # type: ignore[misc]
