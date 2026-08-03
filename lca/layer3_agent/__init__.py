"""L3 Agent 抽象层 —— 单 Agent 封装 + 团队编排。

L3 层职责：
    将 L2 的 CognitiveRuntime 封装为 CognitiveAgent（单 Agent 执行单元），
    并通过 TeamOrchestrator + TeamProcessStrategy 实现多 Agent 编排。
    支持 TeamProcess 族内拓扑：hierarchical / sequential / parallel /
    handoff / swarm / debate / graph（见 ADR-0027 编排族）。
    组合期封闭对象图在 L4；L3 只持有句柄并 run（ADR-0029）。
"""

from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer3_agent.orchestration_registry import TeamProcessStrategyRegistry
from lca.layer3_agent.team_orchestrator import TeamOrchestrator

__all__ = [
    "CognitiveAgent",
    "TeamOrchestrator",
    "TeamProcessStrategyRegistry",
]
