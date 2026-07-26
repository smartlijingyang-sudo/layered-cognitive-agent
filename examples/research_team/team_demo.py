"""
LCA Framework Demo —— Multi-Agent Team 协作
=============================================

运行方式：
    cd layered-cognitive-agent
    python -m examples.research_team.team_demo
"""

from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.tool_protocol.calculator_tool import CalculatorTool
from lca.layer4_app.api import Agent, MultiAgentTeam


async def main() -> None:
    llm = MockLLMAdapter()
    calculator = CalculatorTool()

    researcher = Agent(
        role="资深行业研究员",
        goal="产出一份有数据支撑的市场分析",
        backstory="十年一线调研经验，擅长交叉验证信息源",
        tools=[calculator],
        llm=llm,
    )

    writer = Agent(
        role="报告撰写专家",
        goal="将研究结果整理为可读性强的报告",
        backstory="资深技术写手，擅长将复杂数据转化为清晰叙述",
        tools=[calculator],
        llm=llm,
    )

    print("=" * 70)
    print("LCA Framework Demo: Multi-Agent Team (Sequential)")
    print("=" * 70)
    print()

    team = MultiAgentTeam(
        members=[researcher, writer],
        process="sequential",
    )

    print("开始执行：team.run('123 乘以 456 等于多少？')")
    print("-" * 70)
    result = await team.run("123 乘以 456 等于多少？")

    print()
    print("=" * 70)
    print("Result:")
    print(f"  status      = {result.status}")
    print(f"  output      = {result.output}")
    print(f"  total_steps = {result.total_steps}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
