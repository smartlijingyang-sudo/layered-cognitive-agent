"""图拓扑操作 —— resolved-counter 模型（ADR-0034 修正）。

核心思路：每个节点维护一个 ``resolved`` 计数器，每当一个前驱完成（执行、跳过、
或条件匹配）时 +1。当 ``resolved[node] == in_degree[node]`` 时节点就绪入队。

这消除了旧 ``remaining`` 模型中多套递减机制互相踩踏的问题：
- 旧模型中 ``cascade_skip`` 和 ``enqueue_ready_targets`` 和 ``_run_branch``
  各自递减 ``remaining``，导致 fan-in 节点被重复触发或永远阻塞。
- 新模型中只有一个入口 ``resolve_successor``，所有路径（执行完成、级联跳过、
  并行分支）统一调用，原子递增 + 到齐入队。

供 GraphStrategy 使用的纯函数工具集：
- ``compute_in_degree``: 一次遍历计算所有节点的入度
- ``resolve_successor``: 前驱完成时调用，递增后继 resolved 计数，到齐则入队
- ``cascade_skip``: 条件边未命中时级联标记跳过，对每个后继调用 resolve_successor
"""

from __future__ import annotations

from collections import deque

from lca.contracts.graph import ExecutionGraph


def compute_in_degree(
    graph: ExecutionGraph,
) -> dict[str, int]:
    """计算每个节点的入度（统计所有类型的入边）。"""
    in_degree: dict[str, int] = dict.fromkeys(graph.nodes, 0)
    for edge in graph.edges:
        in_degree[edge.target] += 1
    return in_degree


def resolve_successor(
    graph: ExecutionGraph,
    target_id: str,
    resolved: dict[str, int],
    in_degree: dict[str, int],
    enqueued: set[str],
    skipped: set[str],
    executed: set[str],
    queue: deque[str],
) -> None:
    """前驱完成（执行/跳过）时调用：递增 resolved，到齐则入队。

    幂等保护：已入队/已执行/已跳过的节点不会重复入队。
    """
    if target_id in enqueued or target_id in executed or target_id in skipped:
        return
    resolved[target_id] += 1
    if resolved[target_id] >= in_degree[target_id]:
        enqueued.add(target_id)
        queue.append(target_id)


def cascade_skip(
    graph: ExecutionGraph,
    node_id: str,
    resolved: dict[str, int],
    in_degree: dict[str, int],
    enqueued: set[str],
    skipped: set[str],
    executed: set[str],
    queue: deque[str],
) -> None:
    """条件边未命中时级联跳过下游节点。

    跳过节点后，对其每个后继调用 ``resolve_successor``——与正常执行完成
    相同的解析路径，确保 fan-in 节点正确收到"前驱已解决"信号。
    """
    skip_queue: deque[str] = deque([node_id])
    while skip_queue:
        nid = skip_queue.popleft()
        if nid in skipped or nid in executed or nid in enqueued:
            continue
        skipped.add(nid)
        for edge in graph.outgoing(nid):
            resolve_successor(
                graph,
                edge.target,
                resolved,
                in_degree,
                enqueued,
                skipped,
                executed,
                queue,
            )
