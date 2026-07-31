"""Supervisor setup — role binding at composition time, not a separate type."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.enums import HookEvent
from lca.contracts.member_status import MemberStatus
from lca.contracts.protocols import AgentTransport
from lca.contracts.protocols.capabilities import (
    AcceptsTeammates,
    HasBrainBodyMemory,
    HasChannel,
    HasHooks,
)
from lca.contracts.protocols.cognition import DecisionGate, SupportsDecisionGate
from lca.layer1_cognitive.member_status.hooks import track_member_status_hook
from lca.layer3_agent.simple_agent import CognitiveAgent


@dataclass(frozen=True)
class SupervisorSetup:
    """What to bind when an agent acts as hierarchical supervisor."""

    channel: AgentTransport | None = None
    teammates_text: str = ""
    member_status: MemberStatus | None = None
    decision_gate: DecisionGate | None = None


def apply_supervisor_setup(agent: CognitiveAgent, setup: SupervisorSetup) -> None:
    """Apply SupervisorSetup once at composition time (in-place)."""
    rt = agent.runtime
    if not isinstance(rt, HasBrainBodyMemory):
        return

    if setup.channel is not None and isinstance(rt.body, HasChannel):
        rt.body.bind_channel(setup.channel)
    if setup.teammates_text and isinstance(rt.brain, AcceptsTeammates):
        rt.brain.set_teammates(setup.teammates_text)

    if setup.member_status is not None and isinstance(rt, HasHooks):
        rt.hooks.register(HookEvent.POST_ACT, track_member_status_hook)

    if setup.decision_gate is not None and isinstance(rt, SupportsDecisionGate):
        rt.install_decision_gate(setup.decision_gate)


# Transitional aliases
SupervisionCapabilities = SupervisorSetup
apply_supervision = apply_supervisor_setup
