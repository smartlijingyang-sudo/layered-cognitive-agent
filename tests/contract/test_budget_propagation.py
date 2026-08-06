"""Budget 配置传播测试 —— 验证单一事实来源。

L0 配置层：确保 Agent 声明的 max_steps 与最终生效的 Budget.max_steps 一致。
"""

from __future__ import annotations

from lca.contracts.models.core.budget import (
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    create_budget,
)


class TestBudgetFactory:
    """Budget 工厂的优先级与传播测试。"""

    def test_default_max_steps(self) -> None:
        budget = create_budget()
        assert budget.max_steps == DEFAULT_MAX_STEPS

    def test_default_max_wall_clock(self) -> None:
        budget = create_budget()
        assert budget.max_wall_clock_seconds == DEFAULT_MAX_WALL_CLOCK_SECONDS

    def test_explicit_max_steps(self) -> None:
        budget = create_budget(max_steps=20)
        assert budget.max_steps == 20

    def test_supervisor_max_steps_propagation(self) -> None:
        """Agent(max_steps=20) → Budget.max_steps == 20，不再是硬编码 10。"""
        budget = create_budget(max_steps=20)
        assert budget.max_steps == 20
        assert not budget.exceeded()

    def test_budget_exceeded(self) -> None:
        budget = create_budget(max_steps=5)
        budget.used_steps = 6
        assert budget.exceeded()

    def test_all_params(self) -> None:
        budget = create_budget(
            max_steps=15,
            max_wall_clock_seconds=60,
            max_tokens=10000,
            max_cost_usd=1.0,
        )
        assert budget.max_steps == 15
        assert budget.max_wall_clock_seconds == 60
        assert budget.max_tokens == 10000
        assert budget.max_cost_usd == 1.0


class TestBudgetRuntimeIntegration:
    """验证 Runtime 使用 create_budget 而非硬编码默认值。"""

    async def test_runtime_respects_max_steps(self) -> None:
        """CognitiveRuntime.run(max_steps=20) 的 Budget 应该生效 20 步。"""
        from lca.contracts.models.core.budget import create_budget

        budget = create_budget(max_steps=20)
        assert budget.max_steps == 20
        budget.used_steps = 15
        assert not budget.exceeded()
        budget.used_steps = 21
        assert budget.exceeded()
