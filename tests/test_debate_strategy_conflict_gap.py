"""默认注册的 'debate' 策略永远只跑 1 轮 —— 回归/特征测试(finding #3)。

场景：两位定价策略师（保守派 vs 激进派）对新品零售价分歧巨大
    （$39.9 vs $59.9），期望 DebateStrategy 能识别分歧、多轮收敛。

实际打通验证：
    1) 通过 L4 `MultiAgentTeam(process="debate")` 走默认注册路径
       （defaults.py: `orch_reg.register("debate", lambda: DebateStrategy(
       conflict_monitor=SimpleConflictMonitor(), ...))`）。
       `SimpleConflictMonitor.check()` 硬编码 `return []`，即"永远无冲突"，
       所以不管两个 Agent 报价差多远，第一轮结束 DebateStrategy 就直接
       仲裁退出，`total_steps` 恒为 1，根本没有"辩论"发生。
    2) 手动构造 DebateStrategy，换上一个真正检测价格分歧的
       PriceConflictMonitor（见 tests/scenario_llm.py），同样的两个
       Agent、同样的分歧，这次能正确跑够 2 轮并收敛到折衷价。

结论：DebateStrategy 本身的多轮收敛机制是好的，问题出在 L4 defaults.py
默认注册给它的 ConflictMonitor 是个永远不报冲突的空壳——这是"预留了
可插拔点，但默认实现没有真正实现该干的事"的典型断链，容易让人误以为
`process="debate"` 开箱即用就有真正的多智能体辩论能力。

这个测试断言的是"当前默认注册的真实行为"（1 轮短路），不是期望行为。
如果未来把默认 conflict_monitor 换成真正检测分歧的实现，第一个测试会
失败，提醒同步更新预期（比如断言 total_steps 应该 > 1）。
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lca.layer4_app.defaults  # noqa: F401 — 触发 register_defaults()
from lca.contracts.protocols import OrchestrationContext
from lca.contracts.role_team import TeamConfig
from lca.layer1_cognitive.brain.map_modules import SimpleStateEvaluator, SimpleTaskCoordinator
from lca.layer3_agent.orchestration_strategies import DebateStrategy
from lca.layer4_app.api import Agent, MultiAgentTeam
from tests.scenario_llm import DebatePricingLLM, PriceConflictMonitor


class TestDebateStrategyConflictGap(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.llm = DebatePricingLLM()
        self.conservative = Agent(
            role="保守派定价策略师", goal="", backstory="", tools=[], llm=self.llm
        )
        self.aggressive = Agent(
            role="激进派定价策略师", goal="", backstory="", tools=[], llm=self.llm
        )

    async def test_KNOWN_GAP_default_l4_debate_shortcircuits_after_one_round(self) -> None:  # noqa: N802
        print("\n=== [debate-conflict-gap] [KNOWN GAP] L4 默认 debate 恒 1 轮短路 ===")
        team = MultiAgentTeam(members=[self.conservative, self.aggressive], process="debate")
        result = await team.run("请给无线降噪耳机制定零售定价")

        self.assertEqual(result.status, "completed")
        # 已知缺陷：不管报价分歧多大，默认 debate 恒 1 轮。
        self.assertEqual(result.total_steps, 1)
        # 采纳的是第一个候选（保守派 $39.9），不是任何"综合双方意见"的结果。
        self.assertIn("$39.9", result.output or "")

    async def test_debate_strategy_converges_over_multiple_rounds_with_real_monitor(
        self,
    ) -> None:
        """证明 DebateStrategy 本身没问题：换个真正干活的 ConflictMonitor 就好了。"""
        print("\n=== [debate-conflict-gap] 接入真实 ConflictMonitor 后应多轮收敛 ===")
        members = [self.conservative._base_agent, self.aggressive._base_agent]
        context = OrchestrationContext(
            members=members,
            config=TeamConfig(process="debate", max_rounds=3),
            supervisor=None,
            transport=None,
            roster_desc="",
        )
        strategy = DebateStrategy(
            conflict_monitor=PriceConflictMonitor(),
            task_coordinator=SimpleTaskCoordinator(),
            state_evaluator=SimpleStateEvaluator(),
        )
        result = await strategy.run(context, "请给无线降噪耳机制定零售定价")

        self.assertEqual(result.status, "completed")
        # 收敛到第二轮的折衷价，证明确实跑了多轮而不是第一轮就仲裁。
        self.assertIn("$49.9", result.output or "")
        self.assertIn("折衷", result.output or "")


if __name__ == "__main__":
    unittest.main()
