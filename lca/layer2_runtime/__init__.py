"""L2 认知运行时层 —— 核心 Loop + StopRule。"""

from lca.layer2_runtime.default_loop_judge import DefaultStopRule
from lca.layer2_runtime.event_emission import make_event_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer2_runtime.strategy_registry import get_global_brain_factory_registry

__all__ = [
    "CognitiveRuntime",
    "DefaultStopOutcomePolicy",
    "DefaultStopRule",
    "get_global_brain_factory_registry",
    "make_event_emitting_hook",
]
