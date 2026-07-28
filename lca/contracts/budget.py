"""Budget 单一事实来源工厂 —— 消除配置分叉。

L0 配置层：系统中所有 Budget 构造必须经过此工厂，
禁止在别处直接 Budget(max_steps=N) 式裸构造并携带默认值。

配置合并优先级：显式传参 > 调用方传入 > 全局默认。
"""

from __future__ import annotations

from lca.contracts.state import Budget

_DEFAULT_MAX_STEPS = 10
_DEFAULT_MAX_WALL_CLOCK_SECONDS = 30


def create_budget(
    max_steps: int = _DEFAULT_MAX_STEPS,
    max_wall_clock_seconds: int = _DEFAULT_MAX_WALL_CLOCK_SECONDS,
    max_tokens: int | None = None,
    max_cost_usd: float | None = None,
) -> Budget:
    """Budget 唯一构造入口。

    所有运行时 Budget 必须由此函数生成，确保 max_steps 等参数
    从 Agent 声明处一路透传，不会出现"声明 20 实际跑 10"的分叉。
    """
    return Budget(
        max_steps=max_steps,
        max_wall_clock_seconds=max_wall_clock_seconds,
        max_tokens=max_tokens,
        max_cost_usd=max_cost_usd,
    )
