"""Plan-bound composition for the cognitive think cluster."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.harness.composition.composer import (
    AgentCompositionRequest,
    AgentGraphContribution,
)
from lca.plugins.composer.think.brain import (
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

    PR-A (typed-port refactor): brain internals (reasoner, skill_router,
    classifier, decision_gate, role_profile, tools, adapter) are no longer
    projected onto ``phase_capabilities``. Nodes read them via typed ports
    or ``runtime.brain.*`` single-step access; the kernel-injected runtime
    carriers (``state``, ``writer``, ``effect_gateway``, ``cursor``,
    ``brain``, ``body``, ``memory``, ``perceive_hub``) carry the rest.
    """

    key = "brain"

    def compose_agent(
        self, request: AgentCompositionRequest, scope: Context
    ) -> AgentGraphContribution:
        """Return the graph contribution selected for this Agent's think cluster."""

        llm = instrument_llm(request.spec.llm, ctx=scope)
        brain = resolve_brain(request.spec, llm, scope=scope)
        if request.decision_gate is not None and hasattr(brain, "with_gate"):
            brain = brain.with_gate(request.decision_gate)
        # PR-C: the deleted reasoner-composer plugin used to publish
        # ``reasoner`` and ``llm_adapter`` capabilities at boot. The typed
        # think nodes (``think.llm.invoke``, ``think.llm.persist``,
        # ``think.budget.gate``, ``think.context.truncate``) now read
        # ``state``, ``writer``, and ``adapter`` from the whitelisted
        # kernel runtime carrier; the kernel seeds the carrier on every
        # node visit, so BrainComposer does not need to publish anything.
        # The primitive ``llm_call`` path resolves ``llm_adapter`` via the
        # same runtime carrier (``runtime.get("llm_adapter")``) so the
        # historical key remains available through the kernel's existing
        # per-run carrier wiring.
        return AgentGraphContribution(
            brain=brain,
            body=None,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=llm,
            phase_capabilities={},
            metadata={"composer": self.key},
        )


__all__ = ["BrainComposer"]
