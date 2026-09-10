"""EdgeSelector (ADR-0218 §3.4 Strategy)。

职责:**只**选下一节点。复用既有 `evaluate_restricted_predicate` DSL — 不变语法,
只换输入。

D5 消费点:NodeGraphDriver.run() 主循环每轮调一次。

边界:
- 不调 executor
- 不 emit 事件
- 不读 yaml(只接收 BundleGraphEdge 序列)
- 不感知 NodeContext / NodeOutput
"""

from __future__ import annotations

from typing import Mapping

from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphEdge,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseResult,
)
from lca.harness.graph.predicate import evaluate_restricted_predicate


def select_edge(
    *,
    current_node_id: str,
    edges: tuple[BundleGraphEdge, ...],
    last_phase_result: PhaseResult,
    artifacts: Mapping[str, object],
) -> BundleGraphEdge | None:
    """从 `current_node_id` 出发的边中,选第一个 when 评估为 True 的。

    返回:
      - BundleGraphEdge:下一节点要走的边(source == current_node_id,when True)
      - None:无 from==current_node_id 的边,或所有 when 都 False → 终止

    行为约定:
      - 按 yaml 中 edges[] 的顺序依次评估,**first-match wins**(确定性)
      - DSL 完全复用老 `evaluate_restricted_predicate`,`result.payload` /
        `result.facts` / `result.next_hints` 都可读
    """
    for edge in edges:
        if edge.source != current_node_id:
            continue
        if evaluate_restricted_predicate(
            edge.when,
            result=last_phase_result,
            artifacts=artifacts,
        ):
            return edge
    return None


__all__ = ["select_edge"]
