"""layer-top — 统一认知执行体层。

重构 LCA 五层架构的 Agent / Team 双协议为单一 Worker 协议，
Task 作为对象形式参数取代裸字符串，支持递归嵌套组合。

契约层见 ``layer_top.contracts``，实现层见 ``layer_top.agent`` / ``layer_top.multiagent``。
"""

from __future__ import annotations

from layer_top.agent import Agent, CognitiveEngine
from layer_top.contracts import Result, Task, Worker
from layer_top.multiagent import MultiAgent, OrchestrationStrategy

__all__ = [
    "Agent",
    "CognitiveEngine",
    "MultiAgent",
    "OrchestrationStrategy",
    "Result",
    "Task",
    "Worker",
]
