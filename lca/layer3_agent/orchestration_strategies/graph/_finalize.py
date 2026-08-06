"""GraphStrategy 结果聚合 —— 从执行结果中提取最终输出。"""

from __future__ import annotations

from lca.contracts.budget import create_budget
from lca.contracts.graph import ExecutionGraph, NodeType
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import Synthesizer
from lca.contracts.result import Result

_AGGREGATOR_TRACE_PREFIX = "graph-agg"


async def finalize_graph_result(
    objective: str,
    graph: ExecutionGraph,
    results: dict[str, Result],
    aggregator_ids: set[str],
    synthesizer: Synthesizer | None,
) -> Result:
    """从图执行结果中提取最终 Result：聚合器 > 终端节点 > synthesizer > 拼接。"""
    if not results:
        return Result.failed("Graph execution produced no results")
    total_steps = sum(r.total_steps for r in results.values())

    for agg_id in aggregator_ids:
        if agg_id in results and results[agg_id].output is not None:
            out = results[agg_id]
            out.total_steps = total_steps
            return out

    agent_ids = [
        nid
        for nid, r in results.items()
        if nid in graph.nodes and graph.nodes[nid].type == NodeType.AGENT and r.output
    ]
    terminal: list[str] = []
    for nid in agent_ids:
        has_agent_successor = any(
            e.target in graph.nodes and graph.nodes[e.target].type == NodeType.AGENT
            for e in graph.outgoing(nid)
        )
        if not has_agent_successor:
            terminal.append(nid)
    chosen = terminal or agent_ids
    parts = [str(results[nid].output) for nid in chosen if results[nid].output]

    if not parts:
        last = next(iter(results.values()))
        last.total_steps = total_steps
        return last
    if len(parts) == 1:
        for nid in chosen:
            if results[nid].output and str(results[nid].output) == parts[0]:
                r = results[nid]
                r.total_steps = total_steps
                return r
    if synthesizer is not None:
        candidates = [results[nid] for nid in chosen if results[nid].output]
        synthesized = await synthesizer.synthesize(objective, candidates)
        synthesized.total_steps = total_steps
        return synthesized
    budget = create_budget()
    budget.used_steps = total_steps
    return Result(
        trace_id=objective[:16],
        status=TaskStatus.COMPLETED,
        final_state_ref="",
        total_steps=total_steps,
        budget_used=budget,
        output="\n".join(parts),
    )
