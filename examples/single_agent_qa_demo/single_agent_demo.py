"""
LCA Framework 端到端 Demo —— 单 Agent 回答单一问题
===================================================

运行方式：
    cd layered-cognitive-agent
    python -m examples.single_agent_qa_demo.single_agent_demo

层级对照（自下而上）：
    L0  基础设施层   —— MockLLMAdapter / CalculatorTool / InMemoryStateStore / ConsoleObservability
    L1  认知组件层   —— ModularBrain(MAP) / SimpleBody / SimpleMemorySystem / EventBus / HookRegistry
    L2  认知运行时层 —— CognitiveRuntime（核心循环）
    L3  Agent抽象层  —— BaseAgent
    L4  应用/编排层  —— Agent(...) 极简入口
"""

from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.tool_protocol.calculator_tool import CalculatorTool
from lca.layer4_app.api import Agent


async def main() -> None:
    llm = MockLLMAdapter()
    calculator = CalculatorTool()

    researcher = Agent(
        role="通用问答助手",
        goal="准确、简洁地回答用户提出的问题",
        backstory="擅长借助工具进行精确计算，不臆测数值结果。",
        tools=[calculator],
        llm=llm,
    )

    print("=" * 70)
    print("LCA Framework Demo: 单 Agent 回答单一问题")
    print("=" * 70)
    print()
    print("开始执行：agent.run('123 乘以 456 等于多少？')")
    print("-" * 70)
    result = await researcher.run("123 乘以 456 等于多少？")

    print()
    print("=" * 70)
    print("Result:")
    print(f"  status      = {result.status}")
    print(f"  output      = {result.output}")
    print(f"  total_steps = {result.total_steps}")
    print(f"  used_steps  = {result.budget_used.used_steps}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
