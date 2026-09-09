"""Plan-bound composition for the cognitive think cluster."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from lca.contracts.capabilities import GATES
from lca.contracts.harness.composition.composer import (
    AgentCompositionRequest,
    AgentGraphContribution,
)
from lca.contracts.mechanisms.capability.capability import (
    MissingCapabilityError,
    require_capability,
)
from lca.harness.graph.execute.subgraph_phase_runner import SUBGRAPH_PHASE_RUNNER_CAPABILITY
from lca.plugins.composer.think.brain import (
    apply_lead_brain,
    instrument_llm,
    resolve_brain,
)

if TYPE_CHECKING:
    from cordis import Context


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
        phase_capabilities: dict[str, object] = {
            "gates": require_capability(scope, GATES.key),
        }
        with contextlib.suppress(MissingCapabilityError):
            phase_capabilities[SUBGRAPH_PHASE_RUNNER_CAPABILITY] = require_capability(
                scope, SUBGRAPH_PHASE_RUNNER_CAPABILITY
            )
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
