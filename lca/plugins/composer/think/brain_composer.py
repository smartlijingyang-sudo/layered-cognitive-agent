"""Plan-bound composition for the cognitive think cluster."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.capabilities import GATES
from lca.contracts.harness.composition.composer import (
    AgentCompositionRequest,
    AgentGraphContribution,
)
from lca.contracts.mechanisms.capability.capability import require_capability
from lca.contracts.protocols import Brain, DecisionGate
from lca.contracts.protocols.think.cognition import (
    DecisionGateAssembler,
)
from lca.plugins.composer.think.brain import (
    apply_lead_brain,
    instrument_llm,
    resolve_brain,
)

if TYPE_CHECKING:
    from cordis import Context


def _resolve_decision_gate(
    brain: Brain,
    gates: DecisionGateAssembler,
) -> DecisionGate | None:
    """Tri-source decision gate resolution for the Think phase.

    Resolution order:
    1. ``brain.decision_gate`` — Brain's own gate (if publicly exposed).
    2. ``brain.agent_gates`` — Brain's agent-scope gate chain.
    3. ``gates.assemble()`` — Scope-level gate assembler from the GATES capability.
    """

    own_gate = getattr(brain, "decision_gate", None)
    if own_gate is not None:
        return own_gate
    agent_gates = getattr(brain, "agent_gates", None)
    if agent_gates is not None:
        return agent_gates
    return gates.assemble()


class BrainComposer:
    """Compose only the think cluster of a plan-bound AgentGraph.

    The narrow module is the cognitive-plane seam: it owns LLM instrumentation,
    Brain resolution, and the optional lead decision gate, while leaving every
    execution, state, and collaboration choice to their dedicated modules.
    """

    key = "brain"

    def compose_agent(
        self, request: AgentCompositionRequest, scope: Context
    ) -> AgentGraphContribution:
        """Return the graph contribution selected for this Agent's think cluster."""

        llm = instrument_llm(request.spec.llm, ctx=scope)
        brain = resolve_brain(request.spec, llm, scope=scope)
        if request.decision_gate is not None:
            brain = apply_lead_brain(brain, request.decision_gate)
        gates = require_capability(scope, GATES.key)
        phase_capabilities: dict[str, object] = {"gates": gates}
        for key, attr in (
            ("phase.think.route", "skill_router"),
            ("phase.think.reason", "reasoner"),
            ("phase.think.classify", "classifier"),
        ):
            value = getattr(brain, attr, None)
            if value is not None:
                phase_capabilities[key] = value
        decision_gate = _resolve_decision_gate(brain, gates)
        if decision_gate is not None:
            phase_capabilities["phase.think.decision_gate"] = decision_gate
        return AgentGraphContribution(
            brain=brain,
            body=None,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=llm,
            phase_capabilities=phase_capabilities,
            metadata={"composer": self.key},
        )


__all__ = ["BrainComposer"]
