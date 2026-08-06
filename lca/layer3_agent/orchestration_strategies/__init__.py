"""编排策略实现包 —— 每种 coordination / lead 路径一个 strategy 类。"""

from lca.layer3_agent.orchestration_strategies.debate import DebateStrategy
from lca.layer3_agent.orchestration_strategies.graph import GraphStrategy
from lca.layer3_agent.orchestration_strategies.handoff import (
    HandoffStrategy,
    RaceStrategy,
)
from lca.layer3_agent.orchestration_strategies.lead import LeadStrategy
from lca.layer3_agent.orchestration_strategies.parallel import ParallelStrategy
from lca.layer3_agent.orchestration_strategies.sequential import SequentialStrategy
from lca.layer3_agent.orchestration_strategies.swarm import SwarmStrategy

__all__ = [
    "DebateStrategy",
    "GraphStrategy",
    "HandoffStrategy",  # 向后兼容别名，下一大版本移除
    "LeadStrategy",
    "ParallelStrategy",
    "RaceStrategy",
    "SequentialStrategy",
    "SwarmStrategy",
]
