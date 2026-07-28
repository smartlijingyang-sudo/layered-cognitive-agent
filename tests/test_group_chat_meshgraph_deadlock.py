"""GroupChat 全连接 mesh 拓扑在 GraphStrategy 上直接死锁 —— 回归/特征测试(finding #4)。

`lca/layer3_agent/group_chat.py::build_group_chat_graph` 生成的是一个
"每个 agent 都能把话传给其他任意 agent"的全连接图，并显式设置
`allow_cycle=True`，文档字符串里写着"通过 GraphStrategy 的轮数控制防止
无限循环"。

但 `GraphStrategy` 的执行引擎（graph/strategy.py + graph/topology.py）
是基于入度（in-degree）的一次性拓扑遍历：只有一个节点的全部前驱都执行完，
它的入度才会归零、才会被 enqueue 执行；节点执行完只会 `executed.add(nid)`
一次，没有"同一节点在下一轮辩论里再跑一次"这种机制。

对一个 2 人全连接 mesh 来说：
    entry -> A
    A -> B, A -> exit
    B -> A, B -> exit

A 的入度是 2（来自 entry 和 B），第一次只有 entry 执行完，A 的入度只降到
1，永远到不了 0——A 自己都不会被 enqueue、不会执行，更不用说 B。

实测结果（见下方测试）：不是卡死/无限循环，而是"静默失败"——`run()`
直接在 while 循环第一轮就把 queue 耗尽，`last_result` 全程是 `None`，
最终返回 `Result.failed("Graph execution produced no results")`，
没有任何异常、没有任何日志能提示"这是因为环形依赖导致的死锁"。

这个测试断言的是"当前的真实行为"，不是期望行为。GroupChat 要真正可用，
GraphStrategy 需要一种"轮次感知"的执行模型（比如显式的 round-robin
发言顺序 + 每轮清空 executed 状态），而不是复用现在这套一次性拓扑排序
引擎；或者 GroupChat 应该改用一个专门的策略实现而不是"预置的 Graph
拓扑模板"。在那之前，不建议在生产场景里用 `process="graph"` +
`build_group_chat_graph` 的组合。
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.protocols import LLMAdapter, OrchestrationContext
from lca.contracts.role_team import TeamConfig
from lca.layer3_agent.group_chat import build_group_chat_graph
from lca.layer3_agent.orchestration_strategies import GraphStrategy
from lca.layer4_app.api import Agent


class _MinimalLLM(LLMAdapter):
    """极简确定性 LLM，只返回 respond 动作。"""

    name = "minimal-mock"

    async def complete(self, prompt: str, **kwargs):
        import json

        return json.dumps({"action_type": "respond", "response_text": "OK", "confidence": 0.5})

    async def stream(self, prompt: str, **kwargs):
        text = await self.complete(prompt, **kwargs)
        for ch in text:
            yield ch


_SAFETY_TIMEOUT_S = 5.0


class TestGroupChatMeshGraphDeadlock(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.llm = _MinimalLLM()
        self.market_analyst = Agent(
            role="市场分析师", goal="", backstory="", tools=[], llm=self.llm
        )
        self.pricing_specialist = Agent(
            role="定价专员", goal="", backstory="", tools=[], llm=self.llm
        )
        self.members = [
            self.market_analyst._base_agent,
            self.pricing_specialist._base_agent,
        ]

    async def test_KNOWN_GAP_two_agent_full_mesh_deadlocks_immediately(self) -> None:  # noqa: N802
        print(
            "\n=== [groupchat-deadlock-gap] [KNOWN GAP] "
            "2 人全连接 mesh 在 GraphStrategy 上第一轮即死锁 ==="
        )
        graph = build_group_chat_graph(["市场分析师", "定价专员"], max_rounds=3)
        context = OrchestrationContext(
            members=self.members,
            config=TeamConfig(process="graph"),
            supervisor=None,
            transport=None,
            roster_desc="",
        )
        strategy = GraphStrategy(execution_graph=graph)

        # 用超时兜底：万一未来实现变成真正的死循环而不是静默失败，
        # 测试也不会无限挂起，而是给出明确的失败信息。
        try:
            result = await asyncio.wait_for(
                strategy.run(context, "群聊测试"), timeout=_SAFETY_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            self.fail(
                f"GraphStrategy.run() 在 {_SAFETY_TIMEOUT_S}s 内未返回，"
                "行为从'静默失败'恶化成了'真正死循环'，需要立即定位。"
            )

        # 已知缺陷：不是任何 agent 真正参与了群聊，而是从第一轮就静默失败。
        self.assertEqual(result.status, "failed")
        self.assertIsNone(result.output)


if __name__ == "__main__":
    unittest.main()
