"""第5.10节：运行结果与异常契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from lca.contracts.state import Budget


@dataclass
class Result:
    trace_id: str
    status: Literal["completed", "failed", "paused", "waiting_human"]
    final_state_ref: str
    total_steps: int
    budget_used: Budget
    schema_version: str = "1.0"
    output: str | None = None
    lessons: list[str] = field(default_factory=list)
    trace_url: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def failed(cls, reason: str) -> Result:
        """构造失败 Result 的工厂方法，消除重复的构造代码块。"""
        return cls(
            trace_id="",
            status="failed",
            final_state_ref="",
            total_steps=0,
            budget_used=None,  # type: ignore[arg-type]
            error=reason,
        )


class ApprovalPendingError(Exception):
    def __init__(self, approval_request: Any):
        self.approval_request = approval_request
        super().__init__("waiting for human approval")


class BudgetExceededError(Exception):
    pass


class ToolExecutionError(Exception):
    """工具执行失败基类。

    ``retryable`` 信号供 SafeExecutor 决定是否重试：
    - ``True``（默认）：瞬时性错误，指数退避重试可能恢复
    - ``False``：确定性错误，重试不会改变结果，应 fail-fast
    """

    retryable: bool = True

    def __init__(self, message: str, last_observation: Any | None = None):
        self.last_observation = last_observation
        super().__init__(message)


class ToolInputError(ToolExecutionError):
    """工具输入校验失败——确定性错误，重试无意义。

    典型场景：必填参数缺失、类型错误、表达式语法非法。
    SafeExecutor 遇到此异常应立即返回失败 Observation，不进入退避循环。
    """

    retryable = False
