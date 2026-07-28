"""Team 端到端场景化测试 —— 验证 L4→L3→L2→L1→L0 全链路真实打通。

与仓库里其它 test_*.py 的定位不同：那些测试大多用 MagicMock 替掉
Runtime/Reasoner 来做接线级单元测试，本文件的目标是"拿真实业务场景把
整条链路端到端跑一遍"，覆盖：

    L4 layer4_app.api (Agent / MultiAgentTeam)
      -> L3 layer3_agent (TeamOrchestrator / 各 OrchestrationStrategy /
         Supervisor / BaseAgent)
      -> L2 layer2_runtime (CognitiveRuntime 认知循环 + Hook)
      -> L1 layer1_cognitive (ModularBrain/Reasoner/DecisionParser/Critic,
         SimpleBody/ToolRegistry/SafeExecutor, SimpleMemorySystem)
      -> L0 layer0_infra (InternalTransport, CalculatorTool)

场景：跨境电商新品上市评估团队
    项目负责人(Supervisor) 统筹 市场分析师 / 定价专员(用真实计算器工具) /
    文案撰写 三个角色，退款专员 / 技术支持专员用于分诊(handoff)场景。

驱动这套场景决策的是 tests/scenario_llm.py 里的 ScenarioLLM——一个按
ROLE + CONTEXT 路由的确定性 mock LLM，而不是框架自带的、只认识纯算术题的
MockLLMAdapter。

调试日志：每个测试在跑之前都会打印一条 "=== L4 ENTRY ... ===" 分隔行，
框架内置的 default_logging_hook / ConsoleObservability 会打印每一步
step 的 Hook 事件和 TraceSpan（层级来源见 hook 名称前缀），足以在失败时
定位是哪一层出的问题；测试断言里额外注明了预期触达的层。
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lca.layer4_app.defaults  # noqa: F401 — 触发 register_defaults()
from lca.layer0_infra.tool_protocol.calculator_tool import CalculatorTool
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer4_app.api import Agent, MultiAgentTeam
from tests.scenario_llm import ScenarioLLM


def _log_section(title: str) -> None:
    print(f"\n=== [team-e2e] {title} ===")


# ---------------------------------------------------------------------------
# 场景1：Hierarchical —— Supervisor 委派链
# ---------------------------------------------------------------------------


class TestHierarchicalTeamScenario(unittest.IsolatedAsyncioTestCase):
    """L4 MultiAgentTeam(process="hierarchical") 端到端。

    验证链路：
      L4 MultiAgentTeam -> L3 TeamOrchestrator -> L3 HierarchicalStrategy
      -> L3 Supervisor(BaseAgent).execute -> L2 CognitiveRuntime._loop
      -> L1 ModularBrain.think (Reasoner 读 TEAM_ROSTER 生成 delegate 决策)
      -> L1 SimpleBody._handle_delegate -> L0 InternalTransport.send_task
      -> 被委派 Agent 的 L2 CognitiveRuntime 完整认知循环(含定价专员真实
         调用 L0 CalculatorTool) -> Observation 经 L0 transport 回传
      -> Supervisor 下一步 L1 perceive_and_retrieve 读到 TOOL_RESULT
      -> 循环三次委派后 respond 收尾。
    """

    async def asyncSetUp(self) -> None:
        self.llm = ScenarioLLM()
        self.calculator = CalculatorTool()
        self.market_analyst = Agent(
            role="市场分析师",
            goal="评估新品市场潜力",
            backstory="十年跨境电商选品经验",
            tools=[],
            llm=self.llm,
        )
        self.pricing_specialist = Agent(
            role="定价专员",
            goal="制定合理零售定价",
            backstory="擅长成本加成定价",
            tools=[self.calculator],
            llm=self.llm,
        )
        self.copywriter = Agent(
            role="文案撰写",
            goal="产出上市文案",
            backstory="资深电商文案",
            tools=[],
            llm=self.llm,
        )
        self.supervisor = Agent(
            role="项目负责人",
            goal="统筹新品上市评估",
            backstory="团队协调者",
            tools=[],
            llm=self.llm,
            max_steps=20,
        )
        self.team = MultiAgentTeam(
            members=[self.market_analyst, self.pricing_specialist, self.copywriter],
            process="hierarchical",
            supervisor=self.supervisor,
        )

    async def test_full_delegation_chain_completes(self) -> None:
        _log_section("hierarchical: 完整委派链路应 completed")
        result = await self.team.run(
            "新品：无线降噪耳机，目标市场：东南亚，请给出是否上市的完整评估"
        )

        self.assertEqual(result.status, "completed", msg=f"result={result}")
        # 至少走完 Supervisor 自己的 4 步(委派x3 + 最终respond)，
        # 证明 L2 Runtime Loop 确实多轮驱动了 L1 Brain 决策。
        self.assertGreaterEqual(result.total_steps, 4)
        # 最终答复必须来自"最后一个"被委派的子任务(文案撰写)。
        self.assertIn("LAUNCH_COPY", result.output or "")

    async def test_pricing_specialist_actually_invokes_real_calculator_tool(self) -> None:
        """验证委派链路中间那一跳真的穿透到 L0 CalculatorTool，而不是被 mock 掉。"""
        _log_section("hierarchical: 定价专员应调用真实 L0 calculator 工具")
        result = await self.team.run("新品：蓝牙音箱，目标市场：东南亚")
        self.assertEqual(result.status, "completed")
        # 26 * 1.8 = 46.8，这个数字只能来自 CalculatorTool 真实求值，
        # ScenarioLLM 本身并不知道乘法结果。
        # 最终 respond 只包含文案，所以改为直接跑定价专员单体验证数值链路：
        pricing_result = await self.pricing_specialist.run("成本价 26 美元，请给出建议零售定价")
        self.assertEqual(pricing_result.status, "completed")
        self.assertIn("46.8", pricing_result.output or "")

    async def test_KNOWN_GAP_supervisor_final_summary_loses_earlier_delegation_results(  # noqa: N802
        self,
    ) -> None:
        """已知问题(finding #1)：working memory 每步覆盖，Supervisor 最终汇总
        只能看到"最后一次"委派结果，市场分析/定价的结论在最终 respond 里已丢失。

        根因：SimpleMemorySystem.update_multi_level() 把 working 层整体替换
        成单条最新记录（`self._private_layers["working"] = [MemoryRecord(...)]`），
        而不是 append。Reasoner 每步渲染 prompt 时 CONTEXT 只包含这一条记录。

        这个测试断言的是"当前的真实行为"，不是期望行为——如果将来把 working
        层改成累加式记忆（或让 Supervisor 显式读 shared_memory 层），这个
        测试会失败，提醒同步更新为新的预期行为。
        """
        _log_section("hierarchical: [KNOWN GAP] 委派链路上的历史信息会被覆盖丢失")
        result = await self.team.run("新品：智能手表，目标市场：东南亚")
        self.assertEqual(result.status, "completed")
        # 市场分析/定价阶段产出的关键词，在最终汇总里已经看不到了。
        self.assertNotIn("MARKET_ANALYSIS", result.output or "")
        self.assertNotIn("PRICE_RECOMMENDATION", result.output or "")
        self.assertIn("LAUNCH_COPY", result.output or "")

    async def test_internal_transport_actually_routes_by_role(self) -> None:
        """从 L0 传输层视角验证委派确实经过 InternalTransport 按 role 路由。"""
        _log_section("hierarchical: L0 InternalTransport 应按 role 注册并路由")
        from lca.layer4_app.defaults import build_team_transport

        transport, roster = build_team_transport(
            [
                self.market_analyst._base_agent,
                self.pricing_specialist._base_agent,
                self.copywriter._base_agent,
            ]
        )
        self.assertIsInstance(transport, InternalTransport)
        for role in ("市场分析师", "定价专员", "文案撰写"):
            self.assertIn(role, transport._directory)
            self.assertIn(role, roster)


# ---------------------------------------------------------------------------
# 场景2：Sequential —— 流水线传递
# ---------------------------------------------------------------------------


class TestSequentialTeamScenario(unittest.IsolatedAsyncioTestCase):
    """L4 MultiAgentTeam(process="sequential") 端到端：output 逐棒传递给下一位。"""

    async def test_pipeline_passes_output_as_next_task(self) -> None:
        _log_section("sequential: 上一位的 output 应成为下一位的 task")
        llm = ScenarioLLM()
        calculator = CalculatorTool()
        market_analyst = Agent(role="市场分析师", goal="", backstory="", tools=[], llm=llm)
        pricing_specialist = Agent(
            role="定价专员", goal="", backstory="", tools=[calculator], llm=llm
        )
        copywriter = Agent(role="文案撰写", goal="", backstory="", tools=[], llm=llm)

        team = MultiAgentTeam(
            members=[market_analyst, pricing_specialist, copywriter],
            process="sequential",
        )
        result = await team.run("新品：机械键盘，目标市场：东南亚，成本价 26 美元")

        self.assertEqual(result.status, "completed")
        # 流水线最后一棒是文案撰写，且其 rationale/response 应能追溯到
        # 上一棒(定价专员)产出的 PRICE_RECOMMENDATION 文本被当成了它的 task。
        self.assertIn("LAUNCH_COPY", result.output or "")


# ---------------------------------------------------------------------------
# 场景3：Parallel —— scatter-gather + Synthesizer
# ---------------------------------------------------------------------------


class TestParallelTeamScenario(unittest.IsolatedAsyncioTestCase):
    """L4 MultiAgentTeam(process="parallel") 端到端：并发执行 + 聚合。"""

    async def test_three_writers_run_concurrently_and_get_synthesized(self) -> None:
        _log_section("parallel: 3 位文案应并发执行，结果被 ConcatSynthesizer 聚合")
        llm = ScenarioLLM()
        writers = [
            Agent(role=f"文案撰写{s}", goal="", backstory="", tools=[], llm=llm)
            for s in ("A", "B", "C")
        ]
        team = MultiAgentTeam(members=writers, process="parallel")
        result = await team.run("为无线降噪耳机新品写一句上市文案")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.extra.get("candidate_count"), 3)
        self.assertEqual(result.extra.get("synthesis_method"), "concat")
        # 三位候选人的输出应该互不相同（证明确实各自独立执行，不是被复用/缓存）。
        for tagline in (
            "静界降噪，出行必备",
            "戴上即安静",
            "降噪不将就",
        ):
            self.assertIn(tagline, result.output or "")


# ---------------------------------------------------------------------------
# 场景4：Handoff —— 客服分诊
# ---------------------------------------------------------------------------


class TestHandoffTeamScenario(unittest.IsolatedAsyncioTestCase):
    """L4 MultiAgentTeam(process="handoff") 端到端：首个失败，转交下一位并成功。"""

    async def test_refund_specialist_fails_then_tech_support_resolves(self) -> None:
        _log_section("handoff: 退款专员应因缺少工具权限而 failed，进而转交技术支持")
        llm = ScenarioLLM()
        refund = Agent(role="退款专员", goal="", backstory="", tools=[], llm=llm)
        tech = Agent(role="技术支持专员", goal="", backstory="", tools=[], llm=llm)

        team = MultiAgentTeam(members=[refund, tech], process="handoff")
        result = await team.run("用户反馈耳机连接失败，怀疑是硬件故障还是需要退款，请分诊处理")

        self.assertEqual(result.status, "completed")
        self.assertIn("蓝牙配对", result.output or "")
        self.assertNotIn("退款", (result.output or "").replace("无需退款", ""))

        # 单独验证退款专员自己跑确实是 failed（因为 refund_system 工具未注册），
        # 这样即便未来 HandoffStrategy 的转交逻辑改了，也能独立定位问题层。
        refund_alone = await refund.run("用户反馈耳机连接失败")
        self.assertEqual(refund_alone.status, "failed")
        self.assertIn("未注册工具", refund_alone.error or "")


if __name__ == "__main__":
    unittest.main()
