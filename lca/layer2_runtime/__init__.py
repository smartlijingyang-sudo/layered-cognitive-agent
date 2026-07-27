"""L2 认知运行时层 —— 核心 Loop。"""

from lca.layer2_runtime.hooks import HOOK_NAMES
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer2_runtime.strategy_registry import StrategyRegistry

__all__ = ["HOOK_NAMES", "CognitiveRuntime", "StrategyRegistry"]
