"""L2 认知运行时层 —— 核心 Loop + StopRule。"""

from lca.layer2_runtime.agent_runtime import AgentPhase
from lca.layer2_runtime.default_stop_rule import DefaultStopRule
from lca.layer2_runtime.event_emission import JournalEmitFn, make_journal_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime

__all__ = [
    "AgentPhase",
    "CognitiveRuntime",
    "DefaultStopOutcomePolicy",
    "DefaultStopRule",
    "JournalEmitFn",
    "make_journal_emitting_hook",
]
