"""layer-top 调用形式演示
=================================

纯调用者视角，不含实现。两个场景展示 Worker + Task 的使用形态。
第二层实现后，替换构造方式即可运行。
"""

# ruff: noqa: F841  -- demo 中变量为占位，仅展示调用形态

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from layer_top.contracts import Task


async def scenario_one_single_agent() -> None:
    """场景一：单 Agent —— 竞品调研。"""
    # ── 构造 Worker（第二层提供 AgentWorker）──
    worker = ...  # AgentWorker(role="竞品分析师", llm=...)

    # ── 构造 Task ──
    task = Task(
        instruction="调研 3 家竞品的 SaaS 定价模型",
        expected_output="对比表格，含定价层级和隐藏费用",
        context=["上季度市场分析报告"],
        delegator="产品总监",
        deadline=datetime.now() + timedelta(hours=8),
    )

    # ── 执行 ──
    result = await worker.execute(task)  # type: ignore[attr-defined]  占位
    print(result.output)


async def scenario_two_nested_team() -> None:
    """场景二：嵌套 Team —— 投研流水线。

    内层 Team（分析组）自身是 Worker，可作为外层 Team 的成员。
    """
    # ── 构造内层 Worker（第二层提供 AgentWorker / TeamWorker）──
    industry = ...  # AgentWorker(role="行业分析师")
    finance = ...  # AgentWorker(role="财务分析师")
    reviewer = ...  # AgentWorker(role="终审官")

    # ── 构造内层 Team（本身是 Worker）──
    analysis_team = ...  # TeamWorker(members=[industry, finance])

    # ── 嵌套：内层 Team 作为外层 Team 的成员 ──
    committee = ...  # TeamWorker(members=[analysis_team, reviewer])

    # ── 构造 Task ──
    task = Task(
        instruction="对目标公司完成投研评估",
        expected_output="投研报告，含行业判断、财务风险、终审意见",
        context=["公司年报", "行业数据库"],
        delegator="投委会主席",
        deadline=datetime.now() + timedelta(days=3),
    )

    # ── 执行 ── 对外层 Team 来说，analysis_team 和 reviewer 都是 Worker
    result = await committee.execute(task)  # type: ignore[attr-defined]  占位
    print(result.output)


async def main() -> None:
    await scenario_one_single_agent()
    await scenario_two_nested_team()


if __name__ == "__main__":
    asyncio.run(main())
