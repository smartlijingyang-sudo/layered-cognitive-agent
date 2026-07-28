"""真实 LLM 团队级端到端测试 —— 需要 LLM_API_KEY 才会执行。

与 tests/test_team_scenario_e2e.py 互补：
  - mock 版用 ScenarioLLM（确定性字符串路由），3 秒跑完，CI 常规门禁。
  - 本版用 resolve_llm_adapter() 解析真实模型，验证 L4→L0 全链路在
    真实模型输出格式漂移下仍能收敛。

运行方式：
  # 本地（需设 LLM_API_KEY）
  pytest -m real_llm -v

  # 无 Key 时自动 skip，不会报错
  pytest  # 默认排除 real_llm marker

断言策略：
  真实模型的措辞不可预测，因此断言结构化事件而非文本内容：
    - result.status == "completed"
    - result.total_steps >= N（证明多轮委派确实发生）
    - result.extra 里的结构化字段
"""

from __future__ import annotations

import os
import unittest

import pytest

from lca.layer0_infra.llm_adapter import load_dotenv_if_present, resolve_llm_adapter
from tests.support.scenario_loader import build_team, load_scenario

# 加载 .env（如果存在）
load_dotenv_if_present()

# 检查是否有可用的真实 LLM
_HAS_REAL_LLM = bool(os.getenv("LLM_API_KEY"))

# 所有测试标记为 real_llm
pytestmark = pytest.mark.real_llm

_SCENARIO_PATH = (
    __import__("pathlib").Path(__file__).resolve().parent
    / "fixtures"
    / "team_scenarios"
    / "ecommerce_launch.yaml"
)


@unittest.skipUnless(_HAS_REAL_LLM, "LLM_API_KEY not set")
class TestRealLLMHierarchicalTeam(unittest.IsolatedAsyncioTestCase):
    """真实 LLM 驱动的 hierarchical 团队测试。"""

    async def asyncSetUp(self) -> None:
        self.llm = resolve_llm_adapter()
        self.spec = load_scenario(_SCENARIO_PATH)
        self.team = build_team(self.spec, "hierarchical", self.llm)

    async def test_full_delegation_chain_completes(self) -> None:
        """Supervisor 应能完成完整委派链路（market→pricing→copy→respond）。"""
        case = self.spec.cases["hierarchical_full_chain"]
        result = await self.team.run(case.objective)

        self.assertEqual(result.status, "completed", msg=f"result={result}")
        min_steps = case.assertions.get("min_steps", 4)
        self.assertGreaterEqual(
            result.total_steps,
            min_steps,
            msg=f"Expected >= {min_steps} steps, got {result.total_steps}",
        )


@unittest.skipUnless(_HAS_REAL_LLM, "LLM_API_KEY not set")
class TestRealLLMSequentialTeam(unittest.IsolatedAsyncioTestCase):
    """真实 LLM 驱动的 sequential 团队测试。"""

    async def asyncSetUp(self) -> None:
        self.llm = resolve_llm_adapter()
        self.spec = load_scenario(_SCENARIO_PATH)
        self.team = build_team(self.spec, "sequential", self.llm)

    async def test_pipeline_completes(self) -> None:
        """Sequential 流水线应能跑完并返回 completed。"""
        case = self.spec.cases["sequential_pipeline"]
        result = await self.team.run(case.objective)
        self.assertEqual(result.status, "completed", msg=f"result={result}")


@unittest.skipUnless(_HAS_REAL_LLM, "LLM_API_KEY not set")
class TestRealLLMParallelTeam(unittest.IsolatedAsyncioTestCase):
    """真实 LLM 驱动的 parallel 团队测试。"""

    async def asyncSetUp(self) -> None:
        self.llm = resolve_llm_adapter()
        self.spec = load_scenario(_SCENARIO_PATH)
        self.team = build_team(self.spec, "parallel", self.llm)

    async def test_scatter_gather_completes(self) -> None:
        """Parallel 并发执行 + 聚合应返回 completed。"""
        case = self.spec.cases["parallel_scatter_gather"]
        result = await self.team.run(case.objective)
        self.assertEqual(result.status, "completed", msg=f"result={result}")
        # 验证并发数
        expected_count = case.assertions.get("extra", {}).get("candidate_count")
        if expected_count:
            self.assertEqual(result.extra.get("candidate_count"), expected_count)


@unittest.skipUnless(_HAS_REAL_LLM, "LLM_API_KEY not set")
class TestRealLLMHandoffTeam(unittest.IsolatedAsyncioTestCase):
    """真实 LLM 驱动的 handoff 团队测试。"""

    async def asyncSetUp(self) -> None:
        self.llm = resolve_llm_adapter()
        self.spec = load_scenario(_SCENARIO_PATH)
        self.team = build_team(self.spec, "handoff", self.llm)

    async def test_handoff_triage_completes(self) -> None:
        """Handoff 分诊应能完成（第一个失败后转交第二个）。"""
        case = self.spec.cases["handoff_triage"]
        result = await self.team.run(case.objective)
        self.assertEqual(result.status, "completed", msg=f"result={result}")


if __name__ == "__main__":
    unittest.main()
