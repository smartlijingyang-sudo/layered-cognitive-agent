"""DecisionGate implementations."""

from lca.layer1_cognitive.brain.decision_gates.artifact_respond_injector import (
    ArtifactRespondInjector,
)
from lca.layer1_cognitive.brain.decision_gates.chained import ChainedDecisionGate
from lca.layer1_cognitive.brain.decision_gates.must_consult_all import (
    MustConsultAllMembers,
)
from lca.layer1_cognitive.brain.decision_gates.terminal_respond import TerminalRespondGate
from lca.layer1_cognitive.brain.decision_gates.tool_loop_breaker import ToolLoopBreakerGate


def build_workspace_agent_gate() -> ChainedDecisionGate:
    """Workspace plane gates applied to every agent (ADR-0051)."""
    return ChainedDecisionGate(
        ToolLoopBreakerGate(),
        TerminalRespondGate(),
        ArtifactRespondInjector(),
    )


__all__ = [
    "ArtifactRespondInjector",
    "ChainedDecisionGate",
    "MustConsultAllMembers",
    "TerminalRespondGate",
    "ToolLoopBreakerGate",
    "build_workspace_agent_gate",
]
