"""DecisionGate implementations and workspace gate chain test helpers.

``OfficeWorksSealer`` moved to ``SimpleBody.finalize`` (v3 section 9.2).
Gate chains assemble via ``GateService`` + ``gates.chain.sequential`` bundle.
Tests may use :func:`build_default_workspace_gate_chain` for the standard 6-gate chain.
"""

from lca.cognition.brain.decision_gates.artifact.respond_injector import (
    ArtifactRespondInjector,
)
from lca.cognition.brain.decision_gates.chained.chained import (
    ChainedDecisionGate,
    record_gate_decided,
)
from lca.cognition.brain.decision_gates.must.consult_all import (
    MustConsultAllMembers,
)
from lca.cognition.brain.decision_gates.office.works_sealer import (
    OfficeWorksSealer,  # deprecated: kept for backwards compat imports
)
from lca.cognition.brain.decision_gates.delivery.satisfied import DeliverySatisfiedGate
from lca.cognition.brain.decision_gates.progress.loop_detector import (
    ProgressLoopDetector,
)
from lca.cognition.brain.decision_gates.repeat.tool_call import RepeatToolCallGate
from lca.cognition.brain.decision_gates.terminal.respond import TerminalRespondGate
from lca.cognition.brain.decision_gates.tool.loop_breaker import ToolLoopBreakerGate
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
    "ChainedDecisionGate",
    "DecisionGate",
    "DeliverySatisfiedGate",
    "MustConsultAllMembers",
    "OfficeWorksSealer",  # deprecated: see module docstring
    "ProgressLoopDetector",
    "RepeatToolCallGate",
    "TerminalRespondGate",
    "ToolLoopBreakerGate",
    "build_default_workspace_gate_chain",
    "build_workspace_agent_gate",
    "record_gate_decided",
]
