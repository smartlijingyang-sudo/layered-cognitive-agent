"""DecisionGate implementations (PR4 update — adds RepeatToolCallGate)."""

from lca.layer1_cognitive.brain.decision_gates.artifact_respond_injector import (
    ArtifactRespondInjector,
)
from lca.layer1_cognitive.brain.decision_gates.chained import (
    ChainedDecisionGate,
    record_gate_decided,
)
from lca.layer1_cognitive.brain.decision_gates.must_consult_all import (
    MustConsultAllMembers,
)
from lca.layer1_cognitive.brain.decision_gates.office_works_sealer import OfficeWorksSealer
from lca.layer1_cognitive.brain.decision_gates.progress_loop_detector import (
    ProgressLoopDetector,
)
from lca.layer1_cognitive.brain.decision_gates.repeat_tool_call import RepeatToolCallGate
from lca.layer1_cognitive.brain.decision_gates.terminal_respond import TerminalRespondGate
from lca.layer1_cognitive.brain.decision_gates.tool_loop_breaker import ToolLoopBreakerGate


def build_workspace_agent_gate() -> ChainedDecisionGate:
    """Workspace plane gates applied to every agent (ADR-0051, PR4).

    Order matters: the chain is left-to-right.

    1. RepeatToolCallGate (warn only) — emits a PolicyFact for the same
       tool called >=3 times in a row.  Does NOT block.
    2. ToolLoopBreakerGate (deny after N failures) — forcibly rewrites
       a failing tool decision to RESPOND.
    3. ProgressLoopDetector (warn → break) — cross-tool no-progress
       detection (warning phase + break phase).
    4. OfficeWorksSealer — flushes Office outputs.
    5. TerminalRespondGate — last-step forced respond for non-producers.
    6. ArtifactRespondInjector — final response text normalization.
    """
    return ChainedDecisionGate(
        RepeatToolCallGate(),
        ToolLoopBreakerGate(),
        ProgressLoopDetector(),
        OfficeWorksSealer(),
        TerminalRespondGate(),
        ArtifactRespondInjector(),
    )


__all__ = [
    "ArtifactRespondInjector",
    "ChainedDecisionGate",
    "MustConsultAllMembers",
    "OfficeWorksSealer",
    "ProgressLoopDetector",
    "RepeatToolCallGate",
    "TerminalRespondGate",
    "ToolLoopBreakerGate",
    "build_workspace_agent_gate",
    "record_gate_decided",
]
