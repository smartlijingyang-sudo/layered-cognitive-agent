"""GraphStrategy 并行分支 fan-in 结果丢失 —— 回归/特征测试(finding #2)。

场景：跨境电商新品上市 DAG 编排
    entry -> 市场分析师 -> parallel(定价专员, 风控专员) -> exit

预期直觉：market 之后并行跑定价和风控两个 agent，最终 Result 应该能体现
两条并行分支的产出（至少不应该悄悄丢掉）。

实际打通验证（见下方测试）：定价专员和风控专员确实都被调用执行了（可以从
调试日志里看到 PRICE_RECOMMENDATION / RISK_REVIEW 两个关键词都出现），
但 GraphStrategy.run() 最终返回的 Result 只是主队列循环里"最后一个经由
非并行路径出队的 agent 节点"的结果 —— 本场景里就是 market 节点自己的
Result，两条并行分支的产出对调用方完全不可见。

根因（见 lca/layer3_agent/orchestration_strategies/graph/strategy.py）：
    - `_execute_parallel_branches()` 把每个分支的 Result 写进本地
      `results: dict[str, Result]`；
    - 但 `run()` 最终 `return last_result` 用的是主 while 循环里的局部变量，
      从未从 `_execute_parallel_branches` 回写；
    - `GraphNode.type` 定义了 "aggregator" 类型，但 GraphStrategy 从未特殊
      处理它 —— fan-in 汇聚节点在类型系统里存在，但执行引擎没有实现。

这个测试断言的是"当前的真实行为"（悄悄丢弃），不是期望行为。如果未来把
`results` dict 接入 aggregator 节点或者让 `run()` 返回值反映并行分支，
这个测试会失败，提醒同步更新为新的预期行为（比如改成断言 `result.output`
同时包含 PRICE_RECOMMENDATION 与 RISK_REVIEW）。
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.graph import ExecutionGraph, GraphEdge, GraphNode
from lca.contracts.protocols import LLMAdapter, OrchestrationContext
from lca.contracts.role_team import TeamConfig
from lca.layer0_infra.tool_protocol.calculator_tool import CalculatorTool
from lca.layer3_agent.orchestration_strategies import GraphStrategy
from lca.layer4_app.api import Agent


class _GraphTestLLM(LLMAdapter):
    """角色感知确定性 LLM，返回特定标记以验证框架行为。"""

    name = "graph-test-mock"

    async def complete(self, prompt: str, **kwargs):
        import json
        import re

        role_m = re.search(r"ROLE:\s*([^\n]+)", prompt)
        role = role_m.group(1).strip() if role_m else ""

        if "市场分析" in role:
            response = "MARKET_ANALYSIS: 市场需求增长，建议进入"
        elif "定价" in role:
            response = "PRICE_RECOMMENDATION: 建议零售价 $46.8"
        elif "风控" in role or "风险" in role:
            response = "RISK_REVIEW: 合规风险低，需关注认证周期"
        else:
            response = "OK"

        return json.dumps({"action_type": "respond", "response_text": response, "confidence": 0.8})

    async def stream(self, prompt: str, **kwargs):
        text = await self.complete(prompt, **kwargs)
        for ch in text:
            yield ch


def _build_fanout_fanin_graph() -> ExecutionGraph:
    graph = ExecutionGraph()
    graph.add_node(GraphNode(id="entry", type="entry"))
    graph.add_node(GraphNode(id="market", type="agent", config={"role": "市场分析师"}))
    graph.add_node(GraphNode(id="pricing", type="agent", config={"role": "定价专员"}))
    graph.add_node(GraphNode(id="risk", type="agent", config={"role": "风控专员"}))
    graph.add_node(GraphNode(id="exit", type="exit"))

    graph.add_edge(GraphEdge(source="entry", target="market"))
    graph.add_edge(GraphEdge(source="market", target="pricing", type="parallel"))
    graph.add_edge(GraphEdge(source="market", target="risk", type="parallel"))
    graph.add_edge(GraphEdge(source="pricing", target="exit"))
    graph.add_edge(GraphEdge(source="risk", target="exit"))
    return graph


class TestGraphStrategyFanInGap(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.llm = _GraphTestLLM()
        self.calculator = CalculatorTool()
        self.market_analyst = Agent(
            role="市场分析师", goal="", backstory="", tools=[], llm=self.llm
        )
        self.pricing_specialist = Agent(
            role="定价专员", goal="", backstory="", tools=[self.calculator], llm=self.llm
        )
        self.risk_reviewer = Agent(role="风控专员", goal="", backstory="", tools=[], llm=self.llm)
        self.members = [
            self.market_analyst._base_agent,
            self.pricing_specialist._base_agent,
            self.risk_reviewer._base_agent,
        ]

    async def test_parallel_branches_do_execute(self) -> None:
        """先证明定价/风控两个并行分支确实被执行了（不是压根没跑）。"""
        print("\n=== [graph-fanin-gap] 独立验证定价/风控分支各自可正常执行 ===")
        pricing_result = await self.pricing_specialist.run("成本价 26 美元，请给出建议零售定价")
        risk_result = await self.risk_reviewer.run("请复核新品上市的合规与物流风险")
        self.assertEqual(pricing_result.status, "completed")
        self.assertEqual(risk_result.status, "completed")
        self.assertIn("PRICE_RECOMMENDATION", pricing_result.output or "")
        self.assertIn("RISK_REVIEW", risk_result.output or "")

    async def test_KNOWN_GAP_final_result_only_reflects_pre_fanout_node(self) -> None:  # noqa: N802
        """已知问题(finding #2)：GraphStrategy 最终返回值丢弃并行分支结果。"""
        print("\n=== [graph-fanin-gap] [KNOWN GAP] 并行分支执行了但结果没体现在最终 Result ===")
        graph = _build_fanout_fanin_graph()
        context = OrchestrationContext(
            members=self.members,
            config=TeamConfig(process="graph"),
            supervisor=None,
            transport=None,
            roster_desc="",
        )
        strategy = GraphStrategy(execution_graph=graph)
        result = await strategy.run(context, "新品：无线降噪耳机，目标市场：东南亚")

        self.assertEqual(result.status, "completed")
        # 当前真实行为：只看得到 market 节点自己的输出。
        self.assertIn("MARKET_ANALYSIS", result.output or "")
        # 已知缺陷：定价与风控两条并行分支的产出对调用方不可见。
        self.assertNotIn("PRICE_RECOMMENDATION", result.output or "")
        self.assertNotIn("RISK_REVIEW", result.output or "")


if __name__ == "__main__":
    unittest.main()
