"""Budget 单一事实来源工厂 —— 消除配置分叉。

L0 配置层：系统中所有 Budget 构造必须经过此工厂，
禁止在别处直接 Budget(max_steps=N) 式裸构造并携带默认值。

配置合并优先级：显式传参 > 调用方传入 > 全局默认。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.state import Budget

DEFAULT_MAX_STEPS: int = 50
"""Default maximum reasoning steps per agent run (LobeHub chat is 400 runtime steps)."""

DEFAULT_TOOL_TIMEOUT_S: int = 5
"""Default timeout (seconds) for tool execution."""

DEFAULT_A2A_TIMEOUT_S: float = 30.0
"""Default HTTP timeout (seconds) for A2A transport."""

DEFAULT_DELEGATION_TIMEOUT_S: float = 300.0
"""Default timeout (seconds) for send_and_wait / member invocation.

单一事实源：Body / MemberInvoker / gate 短路一律引用本常量，
禁止在实现层再私藏第二套默认超时（ADR-0049）。
"""

DEFAULT_MAX_WALL_CLOCK_SECONDS: int = 300
"""Default wall-clock timeout for a single agent invocation (seconds)."""

DEFAULT_RUN_WALL_CLOCK_SECONDS: int = 900
"""Gateway run-level wall clock — shared by team pipeline members (ADR-0051)."""

TERMINAL_RESERVE_STEPS: int = 1
"""Steps reserved for terminal respond; tool actions capped at max_steps - this."""

TOOL_LOOP_BREAK_THRESHOLD: int = 3
"""Consecutive identical tool failures or no-progress repeats before circuit breaker fires."""

# Minimum step budget when an agent is composed as team lead.
LEAD_MIN_MAX_STEPS: int = 20

# partial 证据达到该字符数才标 usable（避免把半个 token 当视角覆盖）
DEFAULT_MIN_USABLE_PARTIAL_CHARS: int = 80

# 超时收割后给成员任务收口的宽限秒数
DEFAULT_TIMEOUT_HARVEST_GRACE_S: float = 2.0


@dataclass(frozen=True)
class BudgetLimits:
    """策略解析后的有效预算值——BudgetPolicy.resolve 的返回类型。"""

    max_steps: int
    max_wall_clock_seconds: int

    def __post_init__(self) -> None:
        if self.max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if self.max_wall_clock_seconds <= 0:
            raise ValueError("max_wall_clock_seconds must be positive")


@dataclass(frozen=True)
class DelegationBudget:
    """单次委派的资源切片（资源平面，ADR-0049）。

    由 RunBudget 派生或由 DelegationSpec 显式覆盖；Body 不得私藏默认。
    """

    timeout_s: float = DEFAULT_DELEGATION_TIMEOUT_S
    max_attempts: int = 3
    min_usable_partial_chars: int = DEFAULT_MIN_USABLE_PARTIAL_CHARS


def create_budget(
    max_steps: int = DEFAULT_MAX_STEPS,
    max_wall_clock_seconds: int | None = DEFAULT_MAX_WALL_CLOCK_SECONDS,
    max_tokens: int | None = None,
    max_cost_usd: float | None = None,
) -> Budget:
    """Budget 唯一构造入口。

    所有运行时 Budget 必须由此函数生成，确保 max_steps 等参数
    从 Agent 声明处一路透传，不会出现"声明 20 实际跑 10"的分叉。

    ``max_wall_clock_seconds`` 传 ``None`` 表示不设墙钟超时（仅靠步数兜底）。
    """
    return Budget(
        max_steps=max_steps,
        max_wall_clock_seconds=max_wall_clock_seconds,
        max_tokens=max_tokens,
        max_cost_usd=max_cost_usd,
    )


def resolve_delegation_timeout_s(
    *,
    explicit_timeout_s: float | None = None,
    deadline_remaining_s: float | None = None,
    run_wall_clock_remaining_s: float | None = None,
    default_timeout_s: float = DEFAULT_DELEGATION_TIMEOUT_S,
) -> float:
    """解析本轮委派可用秒数：显式 > deadline 剩余 > min(默认, run 剩余) > 默认。

    返回值始终 ``>= 0``；0 表示已无预算，调用方应立即失败而不派发。
    """
    if explicit_timeout_s is not None:
        return max(0.0, float(explicit_timeout_s))
    if deadline_remaining_s is not None:
        return max(0.0, float(deadline_remaining_s))
    if run_wall_clock_remaining_s is not None:
        return max(0.0, min(default_timeout_s, float(run_wall_clock_remaining_s)))
    return max(0.0, float(default_timeout_s))
