"""L2 认知运行时层 —— 固定循环与阶段解释。"""

from lca.layer2_runtime.agent_runtime import AgentPhase
from lca.layer2_runtime.event_emission import JournalEmitFn, make_journal_emitting_hook
from lca.layer2_runtime.runtime_loop import CognitiveRuntime

__all__ = [
    "AgentPhase",
    "CognitiveRuntime",
    "JournalEmitFn",
    "make_journal_emitting_hook",
]
