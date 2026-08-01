"""layer-top 调用形式演示
=================================

纯调用者视角，两个场景展示 Agent / MultiAgent 的使用形态。
brain / body / memory 和 strategy 是下一层概念，用 ... 占位。
"""

# ruff: noqa: F841  -- demo 中变量为占位，仅展示调用形态

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from layer_top import Agent, MultiAgent, Task
from lca.contracts.role_team import RoleProfile


async def scenario_one_single_agent() -> None:
    """场景一：单 Agent —— 竞品调研。"""
    # ── 构造 Agent（brain/body/memory 是下一层概念）──
    analyst = Agent(
        identity=RoleProfile(
            role="竞品分析师",
            goal="产出竞品定价对比",
            backstory="资深 SaaS 市场研究员",
            tool_permission_manifest=...,  # 下一层提供
        ),
        brain=...,  # Brain 实现（下一层）
        body=...,  # Body 实现（下一层）
        memory=...,  # Memory 实现（下一层）
    )

    # ── 构造 Task ──
    task = Task(
        instruction="调研 3 家竞品的 SaaS 定价模型",
        expected_output="对比表格，含定价层级和隐藏费用",
        context=["上季度市场分析报告"],
        delegator="产品总监",
        deadline=datetime.now() + timedelta(hours=8),
    )

    # ── 执行 ──
    result = await analyst.execute(task)
    if result.success:
        print(result.output)
    else:
        print(f"失败: {result.error}")


async def scenario_two_nested_team() -> None:
    """场景二：嵌套 MultiAgent —— 投研流水线。

    内层 MultiAgent（分析组）自身是 Worker，可作为外层 MultiAgent 的成员。
    """
    # ── 构造内层 Agent ──
    industry = Agent(
        identity=RoleProfile(
            role="行业分析师",
            goal="产出行业判断",
            backstory="十年 TMT 行业研究",
            tool_permission_manifest=...,
        ),
        brain=...,
        body=...,
        memory=...,
    )
    finance = Agent(
        identity=RoleProfile(
            role="财务分析师",
            goal="产出财务风险评估",
            backstory="CPA + CFA 双证",
            tool_permission_manifest=...,
        ),
        brain=...,
        body=...,
        memory=...,
    )
    reviewer = Agent(
        identity=RoleProfile(
            role="终审官",
            goal="出具终审意见",
            backstory="投委会资深委员",
            tool_permission_manifest=...,
        ),
        brain=...,
        body=...,
        memory=...,
    )

    # ── 构造内层 MultiAgent（本身是 Worker）──
    analysis_team = MultiAgent(
        members=[industry, finance],
        strategy=...,  # OrchestrationStrategy 实现（下一层）
    )

    # ── 嵌套：内层 MultiAgent 作为外层 MultiAgent 的成员 ──
    committee = MultiAgent(
        members=[analysis_team, reviewer],
        strategy=...,
    )

    # ── 构造 Task ──
    task = Task(
        instruction="对目标公司完成投研评估",
        expected_output="投研报告，含行业判断、财务风险、终审意见",
        context=["公司年报", "行业数据库"],
        delegator="投委会主席",
        deadline=datetime.now() + timedelta(days=3),
    )

    # ── 执行 ── 对外层来说，analysis_team 和 reviewer 都是 Worker
    result = await committee.execute(task)
    if result.success:
        print(result.output)
    else:
        print(f"失败: {result.error}")


async def main() -> None:
    await scenario_one_single_agent()
    await scenario_two_nested_team()


if __name__ == "__main__":
    asyncio.run(main())
