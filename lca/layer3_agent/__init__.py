"""L3 Agent 抽象层 —— 单 Agent 封装 + 团队编排。

L3 层职责：
    将 L2 的 CognitiveRuntime 封装为 CognitiveAgent（单 Agent 执行单元），
    并通过 TeamOrchestrator + TeamProcessStrategy 实现多 Agent 编排。
    支持六种编排模式：hierarchical / sequential / parallel / handoff / debate / graph。
    所有策略通过注册表解析，L3 不含 if/elif 业务分发。
"""

from lca.layer3_agent.orchestration_registry import (
    TeamProcessBrainFactoryRegistry,
    get_global_orchestration_registry,
)
from lca.layer3_agent.simple_agent import BaseAgent, CognitiveAgent
from lca.layer3_agent.team_orchestrator import TeamOrchestrator

__all__ = [
    "BaseAgent",
    "CognitiveAgent",
    "TeamOrchestrator",
    "TeamProcessBrainFactoryRegistry",
    "get_global_orchestration_registry",
]
