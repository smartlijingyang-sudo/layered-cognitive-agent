"""GroupChat —— 基于 ExecutionGraph 的全连接 mesh 预置模板。

不是独立的 OrchestrationStrategy，而是 Graph 的一种预置拓扑：
- 全连接 mesh：每个 Agent 节点都有边到其他所有 Agent 节点
- max_rounds 熔断：通过 GraphStrategy 的轮数控制防止无限循环
- 条件边：每个 Agent 可以选择把话传给谁（或结束对话）

生产环境慎用：token 贵、容易 drift、难调试（ADR-0008 定位）。
"""

from __future__ import annotations

from lca.contracts.graph import ExecutionGraph, GraphEdge, GraphNode, NodeType


def build_group_chat_graph(
    roles: list[str],
    max_rounds: int = 5,
    allow_all_messages: bool = True,
) -> ExecutionGraph:
    """构建全连接 mesh 拓扑的 ExecutionGraph。

    拓扑结构：
        entry → agent_1 ⇄ agent_2 ⇄ ... ⇄ agent_n → exit

    每个 agent 节点都有 fixed 边到所有其他 agent 节点（全连接），
    以及到 exit 的边（允许任何 agent 结束对话）。

    Args:
        roles: 参与群聊的 Agent 角色列表。
        max_rounds: 最大轮数（信息性，实际由 GraphStrategy 控制）。
        allow_all_messages: 是否允许全连接（True）还是只允许顺序传递（False）。

    Returns:
        可直接传给 GraphStrategy 的 ExecutionGraph。
    """
    graph = ExecutionGraph(allow_cycle=True)

    graph.add_node(GraphNode(id="entry", type=NodeType.ENTRY))
    graph.add_node(GraphNode(id="exit", type=NodeType.EXIT))

    for role in roles:
        graph.add_node(GraphNode(id=role, type=NodeType.AGENT, config={"role": role}))

    # entry → 第一个 agent
    if roles:
        graph.add_edge(GraphEdge(source="entry", target=roles[0]))

    # 全连接 mesh：每个 agent 到其他所有 agent
    if allow_all_messages:
        for src_role in roles:
            for tgt_role in roles:
                if src_role != tgt_role:
                    graph.add_edge(GraphEdge(source=src_role, target=tgt_role))
            # 每个 agent 也可以结束对话
            graph.add_edge(GraphEdge(source=src_role, target="exit"))
    else:
        # 顺序传递：agent_i → agent_{i+1}
        for i in range(len(roles) - 1):
            graph.add_edge(GraphEdge(source=roles[i], target=roles[i + 1]))
        if roles:
            graph.add_edge(GraphEdge(source=roles[-1], target="exit"))

    return graph
