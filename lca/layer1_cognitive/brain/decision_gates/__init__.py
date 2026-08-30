"""DecisionGate implementations and explicit GateChainComposer compatibility helpers.

``OfficeWorksSealer`` 已迁至 ``SimpleBody.finalize``（v3 §9.2 手平面
副作用点）。决策链不再包含；文件保留为 deprecated 桩，便于旧调用方
import 仍能解析。

Gate 链的默认实现由组合层的 ``gate_chain_composer`` seam 提供。此模块
不再拥有默认装配权；兼容辅助函数仅消费调用方明确传入的 composer。
"""

from lca.contracts.protocols.cognition import DecisionGate
from lca.contracts.protocols.gate_chain_composer import GateChainComposer
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


def build_workspace_agent_gate() -> DecisionGate:
    """Reject the retired implicit default-chain construction path.

    New composition must obtain ``gate_chain_composer`` from the plugin tree and
    call :func:`build_workspace_agent_gate_with_composer` with that explicit
    dependency. The retained name gives legacy callers a direct migration error
    instead of silently bypassing the selected seam implementation.
    """

    raise RuntimeError(
        "build_workspace_agent_gate() no longer constructs a default Gate chain; "
        "inject GateChainComposer from the plugin tree and call "
        "build_workspace_agent_gate_with_composer(composer) instead"
    )


def build_workspace_agent_gate_with_composer(composer: GateChainComposer) -> DecisionGate:
    """Build a workspace Gate chain from an explicitly injected composer."""

    return composer.compose()


__all__ = [
    "ArtifactRespondInjector",
    "ChainedDecisionGate",
    "DecisionGate",
    "GateChainComposer",
    "MustConsultAllMembers",
    "OfficeWorksSealer",  # deprecated: see module docstring
    "ProgressLoopDetector",
    "RepeatToolCallGate",
    "TerminalRespondGate",
    "ToolLoopBreakerGate",
    "build_workspace_agent_gate",
    "build_workspace_agent_gate_with_composer",
    "record_gate_decided",
]
