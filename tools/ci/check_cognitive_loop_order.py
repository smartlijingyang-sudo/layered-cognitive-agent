#!/usr/bin/env python3
"""CI 15.4：验证默认 Profile 的声明式认知阶段拓扑。

ADR-0075 移除了 ``CognitiveRuntime._loop``。运行顺序由编译后的
``CognitivePhaseGraphPlan`` 表达，因此本检查通过真实 Profile 编译验证：

``perceive → think → act → reflect → remember → stop``。

它同时拒绝非声明式默认计划和缺少相邻因果边的图，防止薄 Runtime 重新承载
硬编码编排逻辑。
"""

from __future__ import annotations

import sys
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PHASES = ("perceive", "think", "act", "reflect", "remember", "stop")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from lca.harness.profile.plan_compiler import compile_plan
    from lca.harness.profile.resolve import resolve_profile

    plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
    if not plan.is_declarative or plan.phase_graph is None:
        print("FAIL: 默认 Profile 未编译为声明式 PhaseGraph")
        return 1
    if not plan.validation_report.is_valid:
        print("FAIL: 默认声明式计划未通过校验")
        return 1

    graph = plan.phase_graph
    phase_by_node = {node.id: node.semantic_phase.value for node in graph.nodes}
    observed = tuple(phase_by_node[node.id] for node in graph.nodes)
    if observed != EXPECTED_PHASES:
        print(f"FAIL: 阶段序列不匹配：期望 {EXPECTED_PHASES}，实际 {observed}")
        return 1

    causal_edges = {
        (phase_by_node[edge.source], phase_by_node[edge.target])
        for edge in graph.edges
        if edge.source in phase_by_node and edge.target in phase_by_node
    }
    missing = tuple(pairwise(EXPECTED_PHASES))
    absent = [edge for edge in missing if edge not in causal_edges]
    if absent:
        print(f"FAIL: 声明式图缺少相邻因果边：{absent}")
        return 1

    print(f"OK: declarative cognitive phase order = {' → '.join(EXPECTED_PHASES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
