"""图算法私有细节 —— 入度计算、级联跳过等拓扑操作。"""

from __future__ import annotations

from collections import deque

from lca.contracts.graph import ExecutionGraph


def compute_in_degree_and_out_edges(
    graph: ExecutionGraph,
) -> tuple[dict[str, int], dict[str, list[int]]]:
    """计算每个节点的入度和出边索引。"""
    in_degree: dict[str, int] = dict.fromkeys(graph.nodes, 0)
    out_edge_indices: dict[str, list[int]] = {nid: [] for nid in graph.nodes}
    for idx, edge in enumerate(graph.edges):
        in_degree[edge.target] += 1
        out_edge_indices[edge.source].append(idx)
    return in_degree, out_edge_indices


def cascade_skip(
    graph: ExecutionGraph,
    node_id: str,
    remaining: dict[str, int],
    skipped: set[str],
    executed: set[str],
    queue: deque[str],
) -> None:
    """条件边未命中时级联跳过下游节点，防止 join 死等。"""
    skip_queue: deque[str] = deque([node_id])
    while skip_queue:
        nid = skip_queue.popleft()
        if nid in skipped or nid in executed:
            continue
        remaining[nid] -= 1
        if remaining[nid] > 0:
            continue
        skipped.add(nid)
        for edge in graph.outgoing(nid):
            if edge.target not in executed:
                skip_queue.append(edge.target)


def enqueue_ready_targets(
    targets: list[str],
    remaining: dict[str, int],
    executed: set[str],
    queue: deque[str],
) -> None:
    """将入度归零且未执行的 target 加入队列。"""
    for target in targets:
        remaining[target] -= 1
        if remaining[target] <= 0 and target not in executed:
            queue.append(target)
