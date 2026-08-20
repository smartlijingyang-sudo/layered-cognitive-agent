"""DecisionGate implementations (PR4 update — adds RepeatToolCallGate; PR6.D.5 drops OfficeWorksSealer).

``OfficeWorksSealer`` 已迁至 ``SimpleBody.finalize``（v3 §9.2 手平面
副作用点）。决策链不再包含；文件保留为 deprecated 桩，便于旧调用方
import 仍能解析，但 ``build_workspace_agent_gate`` 不再实例化它。
"""

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
from lca.layer1_cognitive.brain.decision_gates.office_works_sealer import (
    OfficeWorksSealer,  # deprecated: kept for backwards compat imports
)
from lca.layer1_cognitive.brain.decision_gates.progress_loop_detector import (
    ProgressLoopDetector,
)
from lca.layer1_cognitive.brain.decision_gates.repeat_tool_call import RepeatToolCallGate
from lca.layer1_cognitive.brain.decision_gates.terminal_respond import TerminalRespondGate
from lca.layer1_cognitive.brain.decision_gates.tool_loop_breaker import ToolLoopBreakerGate


def build_workspace_agent_gate() -> ChainedDecisionGate:
    """Workspace plane gates applied to every agent (ADR-0051, PR4 + PR6.D.5).

    Order matters: the chain is left-to-right.

    1. RepeatToolCallGate (warn only) — emits a PolicyFact for the same
       tool called >=3 times in a row.  Does NOT block.
    2. ToolLoopBreakerGate (deny after N failures) — forcibly rewrites
       a failing tool decision to RESPOND.
    3. ProgressLoopDetector (warn → break) — cross-tool no-progress
       detection (warning phase + break phase).
    4. TerminalRespondGate — last-step forced respond for non-producers.
    5. ArtifactRespondInjector — final response text normalization.

    Note (PR6.D.5): ``OfficeWorksSealer`` removed — its world-side-effect
    call migrated to ``SimpleBody.finalize``.
    """
    return ChainedDecisionGate(
        RepeatToolCallGate(),
        ToolLoopBreakerGate(),
        ProgressLoopDetector(),
        TerminalRespondGate(),
        ArtifactRespondInjector(),
    )


__all__ = [
    "ArtifactRespondInjector",
    "ChainedDecisionGate",
    "MustConsultAllMembers",
    "OfficeWorksSealer",  # deprecated: see module docstring
    "ProgressLoopDetector",
    "RepeatToolCallGate",
    "TerminalRespondGate",
    "ToolLoopBreakerGate",
    "build_workspace_agent_gate",
    "record_gate_decided",
]
