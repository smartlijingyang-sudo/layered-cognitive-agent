"""编排策略实现包 —— hierarchical / choreography / graph。

ChoreographyStrategy 用 dispatch table 统一 sequential / parallel /
handoff / debate 四种外部编排拓扑；HierarchicalStrategy 和 GraphStrategy
因执行模型不同保持独立。
"""

from lca.layer3_agent.orchestration_strategies.choreography import ChoreographyStrategy
from lca.layer3_agent.orchestration_strategies.graph import GraphStrategy
from lca.layer3_agent.orchestration_strategies.hierarchical import HierarchicalStrategy

__all__ = [
    "ChoreographyStrategy",
    "GraphStrategy",
    "HierarchicalStrategy",
]
