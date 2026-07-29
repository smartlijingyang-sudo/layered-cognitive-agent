"""GroupChat demoted."""

from __future__ import annotations

from lca.contracts.graph import ExecutionGraph


def build_group_chat_graph(
    roles: list[str], max_rounds: int = 5, allow_all_messages: bool = True
) -> ExecutionGraph:
    del roles, max_rounds, allow_all_messages
    raise NotImplementedError(
        "GroupChat mesh 不再通过 GraphStrategy 执行（循环拓扑与 DAG 引擎不兼容）。"
        "请使用 MultiAgentTeam(process='debate'|'sequential'|'handoff')，"
        "或构造严格 DAG 的 ExecutionGraph 注入 GraphStrategy。"
    )
