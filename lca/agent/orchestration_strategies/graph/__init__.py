"""GraphStrategy 子包 —— DAG 工作流引擎。

将 ExecutionGraph（节点 + 有向边）编译为拓扑排序执行计划，
支持 fan-in/fan-out、条件分支、并行分支、聚合节点。
仅接受严格 DAG（无环），循环拓扑请使用 debate 策略。
"""

from lca.agent.orchestration_strategies.graph.strategy import GraphStrategy

__all__ = ["GraphStrategy"]
