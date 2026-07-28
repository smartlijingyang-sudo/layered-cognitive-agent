"""
LCA Framework —— 极简 Demo：Agent 初始化并运行
================================================

运行方式：
    python3 lca_single_agent_demo.py

无需任何类定义，全部组件从框架各层导入。
"""

from __future__ import annotations

import asyncio
import os

from lca.layer0_infra.llm_adapter import load_dotenv_if_present, resolve_llm_adapter
from lca.layer0_infra.tool_protocol import CalculatorTool, GetWeatherTool
from lca.layer4_app import Agent


def _make_agent(llm) -> Agent:
    return Agent(
        role="通用问答助手",
        goal="准确、简洁地回答用户提出的问题",
        backstory="擅长借助工具进行精确计算和天气查询，不臆测数值结果。",
        tools=[CalculatorTool(), GetWeatherTool()],
        llm=llm,
    )


def _print_result(result) -> None:
    print(f"  status      = {result.status}")
    print(f"  output      = {result.output}")
    print(f"  total_steps = {result.total_steps}")
    print(f"  used_steps  = {result.budget_used.used_steps}")
    print("=" * 70)


async def main() -> None:
    load_dotenv_if_present()

    llm = resolve_llm_adapter()
    if llm.name == "mock-llm":
        print("[配置] 未检测到 LLM_API_KEY，降级使用 MockLLMAdapter")
    else:
        print(
            f"[配置] LLM={os.getenv('LLM_MODEL', 'gpt-4.1')} "
            f"base_url={os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1')}"
        )

    # 场景 1：算术计算
    print("=" * 70)
    print("场景 1：agent.run('123 乘以 456 等于多少？')")
    print("=" * 70)
    result = await _make_agent(llm).run("123 乘以 456 等于多少？")
    _print_result(result)

    # 场景 2：天气查询
    print()
    print("=" * 70)
    print("场景 2：agent.run('东京现在天气怎么样？')")
    print("=" * 70)
    result = await _make_agent(llm).run("东京现在天气怎么样？")
    _print_result(result)


if __name__ == "__main__":
    asyncio.run(main())
