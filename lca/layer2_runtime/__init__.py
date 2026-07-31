"""L2 认知运行时层 —— 核心 Loop + StopRule。"""

from lca.layer2_runtime.default_loop_judge import DefaultStopRule
from lca.layer2_runtime.event_emission import HOOK_NAMES, make_event_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStepOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer2_runtime.strategy_registry import BrainFactoryRegistry

__all__ = [
    "HOOK_NAMES",
    "BrainFactoryRegistry",
    "CognitiveRuntime",
    "DefaultStepOutcomePolicy",
    "DefaultStopRule",
    "make_event_emitting_hook",
]
