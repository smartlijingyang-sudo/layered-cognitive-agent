"""
LCA Framework Demo —— 可插拔性验证
====================================

演示如何在不修改框架源码的情况下：
1. 自定义 MemorySystem（装饰器模式，包一层日志）
2. 自定义 Observability 实现
3. 通过注册表名字或自定义实例注入 Agent

运行方式：
    cd layered-cognitive-agent
    python3.11 -m examples.pluggability_demo.pluggability_demo
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lca.contracts.decision import Observation, Reflection
from lca.contracts.state import TypedState
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.registry import get_global_registry
from lca.layer0_infra.tool_protocol.calculator_tool import CalculatorTool
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer4_app.api import Agent


class LoggingMemorySystem:
    """装饰器模式的自定义 MemorySystem —— 在标准实现外包一层日志。"""

    def __init__(self) -> None:
        self._inner = SimpleMemorySystem()
        self.perceive_count = 0
        self.update_count = 0

    async def perceive_and_retrieve(self, state: TypedState) -> TypedState:
        self.perceive_count += 1
        print(f"  [LoggingMemory] perceive_and_retrieve #{self.perceive_count}")
        return await self._inner.perceive_and_retrieve(state)

    async def update_multi_level(
        self, state: TypedState, observation: Observation, reflection: Reflection
    ) -> None:
        self.update_count += 1
        print(
            f"  [LoggingMemory] update_multi_level #{self.update_count} success={observation.success}"
        )
        await self._inner.update_multi_level(state, observation, reflection)


class MinimalObservability:
    """极简可观测实现 —— 只输出工具调用。"""

    def emit_span(self, span) -> None:
        if span.name.startswith("tool."):
            dur = None
            if span.ended_at:
                dur = int((span.ended_at - span.started_at).total_seconds() * 1000)
            print(f"  [MinObs] {span.name} dur_ms={dur}")


async def main() -> None:
    llm = MockLLMAdapter()
    calculator = CalculatorTool()

    # --- 方式 1: 通过注册表名字注入自定义 MemorySystem ---
    reg = get_global_registry()
    reg.register("memory", "logging", LoggingMemorySystem)

    print("=" * 70)
    print("Pluggability Demo: 自定义 MemorySystem (通过注册表名字)")
    print("=" * 70)
    print()

    agent_with_logging_memory = Agent(
        role="通用问答助手",
        goal="准确、简洁地回答用户提出的问题",
        backstory="擅长借助工具进行精确计算。",
        tools=[calculator],
        llm=llm,
        memory="logging",
    )

    print("开始执行：agent.run('123 乘以 456 等于多少？')")
    print("-" * 70)
    result = await agent_with_logging_memory.run("123 乘以 456 等于多少？")

    print()
    print("=" * 70)
    print(f"Result: status={result.status}, output={result.output}")
    print(f"  total_steps={result.total_steps}")
    print("=" * 70)

    # --- 方式 2: 直接传入自定义 Observability 实例 ---
    print()
    print("=" * 70)
    print("Pluggability Demo: 自定义 Observability (直接传实例)")
    print("=" * 70)
    print()

    my_obs = MinimalObservability()

    agent_with_custom_obs = Agent(
        role="通用问答助手",
        goal="准确、简洁地回答用户提出的问题",
        backstory="擅长借助工具进行精确计算。",
        tools=[calculator],
        llm=llm,
        observability=my_obs,
    )

    print("开始执行：agent.run('789 加 100 等于多少？')")
    print("-" * 70)
    result2 = await agent_with_custom_obs.run("789 加 100 等于多少？")

    print()
    print("=" * 70)
    print(f"Result: status={result2.status}, output={result2.output}")
    print(f"  total_steps={result2.total_steps}")
    print("=" * 70)

    # --- 验证注册表列表 ---
    print()
    print("已注册的 memory 实现:", reg.list("memory"))
    print("已注册的 observability 实现:", reg.list("observability"))


if __name__ == "__main__":
    asyncio.run(main())
