"""L2 认知运行时层 —— 核心 Loop + StepOutcomePolicy。"""

from lca.layer2_runtime.hooks import HOOK_NAMES, make_event_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStepOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer2_runtime.strategy_registry import StrategyRegistry

__all__ = [
    "HOOK_NAMES",
    "CognitiveRuntime",
    "DefaultStepOutcomePolicy",
    "StrategyRegistry",
    "make_event_emitting_hook",
]
