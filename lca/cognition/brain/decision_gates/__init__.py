"""DecisionGate implementations and workspace gate chain test helpers.

``OfficeWorksSealer`` moved to ``SimpleBody.finalize`` (v3 section 9.2).
Gate chains assemble via ``GateService`` + ``gates.chain.sequential`` bundle.
Tests may use :func:`build_default_workspace_gate_chain` for the standard 6-gate chain.
"""

from lca.cognition.brain.decision_gates.artifact import ArtifactRespondInjector
from lca.cognition.brain.decision_gates.auth import AuthUrlProvenanceGate
from lca.cognition.brain.decision_gates.chained import (
    ChainedDecisionGate,
    record_gate_decided,
)
from lca.cognition.brain.decision_gates.consult import MustConsultAllMembers
from lca.cognition.brain.decision_gates.delivery import DeliverySatisfiedGate
from lca.cognition.brain.decision_gates.loop_guards import (
    ProgressLoopDetector,
    ToolLoopBreakerGate,
)
from lca.cognition.brain.decision_gates.multi_tool_loop import MultiToolLoopBreakerGate
from lca.cognition.brain.decision_gates.office import OfficeWorksSealer
from lca.cognition.brain.decision_gates.repeat import RepeatToolCallGate
from lca.cognition.brain.decision_gates.terminal import TerminalRespondGate
from lca.cognition.convergence.runtime import ConvergenceRuntime
from lca.contracts.protocols.think.cognition import DecisionGate


def build_default_workspace_gate_chain() -> DecisionGate:
    """Standard 6-gate workspace chain (GateService / gates.chain.sequential SSOT)."""
    runtime = ConvergenceRuntime.default()
    return ChainedDecisionGate(
        RepeatToolCallGate(),
        ToolLoopBreakerGate(),
        ProgressLoopDetector(),
        DeliverySatisfiedGate(runtime),
        TerminalRespondGate(),
        ArtifactRespondInjector(),
    )


def build_workspace_agent_gate() -> DecisionGate:
    """Reject the retired implicit default-chain construction path."""
    raise RuntimeError(
        "build_workspace_agent_gate() no longer constructs a default Gate chain; "
        "use gates.assemble from profile or build_default_workspace_gate_chain() in tests"
    )


__all__ = [
    "ArtifactRespondInjector",
    "AuthUrlProvenanceGate",
    "ChainedDecisionGate",
    "DecisionGate",
    "DeliverySatisfiedGate",
    "MultiToolLoopBreakerGate",
    "MustConsultAllMembers",
    "OfficeWorksSealer",
    "ProgressLoopDetector",
    "RepeatToolCallGate",
    "TerminalRespondGate",
    "ToolLoopBreakerGate",
    "build_default_workspace_gate_chain",
    "build_workspace_agent_gate",
    "record_gate_decided",
]
