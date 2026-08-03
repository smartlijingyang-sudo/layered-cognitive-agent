"""SupervisorBinder + consultation control-plane discipline (ADR-0026)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lca.contracts.consultation import (
    CONSULTATION_FIELD_WHITELIST,
    HierarchicalConsultation,
    assert_consultation_field_whitelist,
)
from lca.contracts.protocols.capabilities import HasChannel
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
from lca.layer1_cognitive.brain.reasoner import SimpleReasoner, SupervisorReasoner
from lca.layer3_agent.simple_agent import CognitiveAgent
from lca.layer3_agent.supervisor_bind import (
    SupervisorBinder,
    SupervisorBindError,
    default_supervisor_cognition_factory,
)


def _profile(role: str = "supervisor") -> RoleProfile:
    return RoleProfile(
        role=role,
        goal=f"goal-{role}",
        backstory="",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


class _Body(HasChannel):
    def __init__(self) -> None:
        self.bound: object | None = None

    def bind_channel(self, transport: object) -> None:
        self.bound = transport


def _agent_with_brain(*, reasoner: object) -> CognitiveAgent:
    body = _Body()
    brain = MagicMock()
    brain.reasoner = reasoner
    brain.install_decision_gate = MagicMock()

    rt = MagicMock()
    rt.body = body
    rt.brain = brain
    rt.memory = MagicMock()
    return CognitiveAgent(rt, _profile())


class TestDefaultCognitionFactory:
    def test_promotes_simple_reasoner(self) -> None:
        simple = SimpleReasoner(
            MagicMock(),
            _profile(),
            "tools",
            templates={"react_prompt": "r", "hierarchical_prompt": "h {teammates}"},
        )
        out = default_supervisor_cognition_factory(simple)
        assert isinstance(out, SupervisorReasoner)
        assert out is not simple

    def test_idempotent_for_supervisor_reasoner(self) -> None:
        sup = SupervisorReasoner(
            MagicMock(),
            _profile(),
            "tools",
            templates={"hierarchical_prompt": "h {teammates}"},
        )
        assert default_supervisor_cognition_factory(sup) is sup

    def test_rejects_unknown_reasoner(self) -> None:
        with pytest.raises(SupervisorBindError, match="cannot install supervisor cognition"):
            default_supervisor_cognition_factory(MagicMock())  # type: ignore[arg-type]


class TestSupervisorBinder:
    def test_bind_promotes_and_installs_gate_and_channel(self) -> None:
        simple = SimpleReasoner(
            MagicMock(),
            _profile(),
            "tools",
            templates={"react_prompt": "r", "hierarchical_prompt": "h {teammates}"},
        )
        agent = _agent_with_brain(reasoner=simple)
        transport = MagicMock()
        policy = MustConsultAllMembers()

        SupervisorBinder().bind(agent, transport=transport, policy=policy)

        assert isinstance(agent.runtime.brain.reasoner, SupervisorReasoner)
        agent.runtime.brain.install_decision_gate.assert_called_once_with(policy)
        assert agent.runtime.body.bound is transport

    def test_bind_idempotent_when_already_supervisor_reasoner(self) -> None:
        sup_r = SupervisorReasoner(
            MagicMock(),
            _profile(),
            "tools",
            templates={"hierarchical_prompt": "h {teammates}"},
        )
        agent = _agent_with_brain(reasoner=sup_r)
        SupervisorBinder().bind(agent, policy=MustConsultAllMembers())
        assert agent.runtime.brain.reasoner is sup_r

    def test_custom_cognition_factory(self) -> None:
        sentinel = SupervisorReasoner(
            MagicMock(),
            _profile(),
            "tools",
            templates={"hierarchical_prompt": "custom {teammates}"},
        )
        simple = SimpleReasoner(
            MagicMock(),
            _profile(),
            "tools",
            templates={"react_prompt": "r"},
        )
        agent = _agent_with_brain(reasoner=simple)
        binder = SupervisorBinder(cognition_factory=lambda _r: sentinel)
        binder.bind(agent)
        assert agent.runtime.brain.reasoner is sentinel

    def test_missing_runtime_capabilities_raises(self) -> None:
        agent = CognitiveAgent(MagicMock(spec=[]), _profile())
        with pytest.raises(SupervisorBindError, match="HasBrainBodyMemory"):
            SupervisorBinder().bind(agent)

    def test_transport_without_channel_raises(self) -> None:
        simple = SimpleReasoner(
            MagicMock(),
            _profile(),
            "tools",
            templates={"react_prompt": "r", "hierarchical_prompt": "h"},
        )
        agent = _agent_with_brain(reasoner=simple)
        agent.runtime.body = object()  # no HasChannel
        with pytest.raises(SupervisorBindError, match="HasChannel"):
            SupervisorBinder().bind(agent, transport=MagicMock())

    def test_gate_without_support_raises(self) -> None:
        simple = SimpleReasoner(
            MagicMock(),
            _profile(),
            "tools",
            templates={"react_prompt": "r", "hierarchical_prompt": "h"},
        )
        agent = _agent_with_brain(reasoner=simple)
        # brain without install_decision_gate
        bare = MagicMock(spec=["reasoner"])
        bare.reasoner = simple
        agent.runtime.brain = bare
        with pytest.raises(SupervisorBindError, match="SupportsDecisionGate"):
            SupervisorBinder().bind(agent, policy=MustConsultAllMembers())

    def test_brain_without_reasoner_raises(self) -> None:
        agent = _agent_with_brain(reasoner=SimpleReasoner(MagicMock(), _profile(), "t"))
        bare = MagicMock(spec=["install_decision_gate"])
        bare.install_decision_gate = MagicMock()
        agent.runtime.brain = bare
        with pytest.raises(SupervisorBindError, match="HasReplaceableReasoner"):
            SupervisorBinder().bind(agent)


class TestConsultationDiscipline:
    def test_whitelist_matches_dataclass(self) -> None:
        assert_consultation_field_whitelist()
        assert "member_status" in CONSULTATION_FIELD_WHITELIST
        assert "extra" not in CONSULTATION_FIELD_WHITELIST

    def test_hierarchical_consultation_alias(self) -> None:
        from lca.contracts.consultation import ConsultationState
        from lca.layer1_cognitive.member_status import InMemoryMemberStatus

        board = InMemoryMemberStatus(role_order=("a",))
        session = HierarchicalConsultation(member_status=board)
        assert isinstance(session, ConsultationState)


class TestSimpleReasonerTeamAgnosticSource:
    """SimpleReasoner must stay free of hierarchical control-plane coupling."""

    def test_source_has_no_team_control_symbols(self) -> None:
        import ast
        from pathlib import Path

        src = Path("lca/layer1_cognitive/brain/reasoner.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        simple_cls = next(
            n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SimpleReasoner"
        )
        names = {node.id for node in ast.walk(simple_cls) if isinstance(node, ast.Name)}
        attrs = {node.attr for node in ast.walk(simple_cls) if isinstance(node, ast.Attribute)}
        banned = {
            "RoleMode",
            "consultation",
            "member_status",
            "teammates",
            "hierarchical_prompt",
            "member_status_text",
            "ConsultationState",
            "HierarchicalConsultation",
        }
        hit = (names | attrs) & banned
        assert not hit, f"SimpleReasoner code must not use {sorted(hit)} (ADR-0026)"
