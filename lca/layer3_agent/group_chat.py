"""GroupChat mesh 拓扑已废弃 —— 保留为显式失败桩。

GroupChat 的全互联消息拓扑（每个 agent 同时收到所有其他 agent 的输出）
构成循环图，与 GraphStrategy 的严格 DAG 引擎不兼容。

替代方案：
- ``debate``  —— 多轮并行表态 + 冲突仲裁，适合共识场景
- ``sequential`` / ``handoff`` —— 链式传递，适合流水线场景
- 自定义 ``ExecutionGraph`` —— 若确实需要类 GroupChat 拓扑，
  请构造严格 DAG 后直接注入 GraphStrategy

本模块保留 ``build_group_chat_graph`` 桩函数，调用时抛出
``NotImplementedError`` 并给出迁移指引。未来若 DAG 引擎支持
SCC 收缩，可在此重新实现。
"""

from __future__ import annotations

from lca.contracts.graph import ExecutionGraph

_DEFAULT_MAX_ROUNDS = 5


def build_group_chat_graph(
    roles: list[str], max_rounds: int = _DEFAULT_MAX_ROUNDS, allow_all_messages: bool = True
) -> ExecutionGraph:
    """构建 GroupChat 全互联图（已废弃，调用即抛异常）。

    Raises:
        NotImplementedError: 始终抛出，附带迁移指引。
    """
    del roles, max_rounds, allow_all_messages
    raise NotImplementedError(
        "GroupChat mesh 不再通过 GraphStrategy 执行（循环拓扑与 DAG 引擎不兼容）。"
        "请使用 MultiAgentTeam(process='debate'|'sequential'|'handoff')，"
        "或构造严格 DAG 的 ExecutionGraph 注入 GraphStrategy。"
    )
