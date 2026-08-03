"""第5.10节：运行结果与异常契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lca.contracts.ids import new_id
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.state import Budget

if TYPE_CHECKING:
    from lca.contracts.decision import Observation
    from lca.contracts.state import AgentState


@dataclass
class Result:
    """Agent / Team 运行的最终结果契约。

    消费方应先检查 ``status``：非 COMPLETED 时 ``budget_used`` 为零值 Budget，
    ``output`` / ``trace_url`` 等可能为 None。
    """

    trace_id: str
    status: TaskStatus
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
            status=TaskStatus.FAILED,
            final_state_ref="",
            total_steps=0,
            budget_used=Budget(),
            error=reason,
        )

    @classmethod
    def from_observation(cls, observation: Observation, task_id: str) -> Result:
        """Bridge an Observation from the channel path into a Result."""
        extra = observation.extra or {}
        source_status = extra.get("source_status")
        if isinstance(source_status, TaskStatus):
            status = source_status
        else:
            status = TaskStatus.COMPLETED if observation.success else TaskStatus.FAILED
        payload = observation.payload
        if isinstance(payload, str):
            output: str | None = payload
        elif payload is not None:
            output = str(payload)
        else:
            output = None
        total_steps = int(extra.get("source_total_steps") or 1)
        trace_id = str(extra.get("source_trace_id") or new_id("trace"))
        return cls(
            trace_id=trace_id,
            status=status,
            final_state_ref=f"transport://{task_id or observation.observation_id}",
            total_steps=total_steps,
            budget_used=Budget(used_steps=total_steps),
            output=output,
            error=observation.error,
        )

    @classmethod
    def from_state(cls, state: AgentState) -> Result:
        """Summarize a final AgentState into a Result."""
        status = TaskStatus.COMPLETED if state.status == TaskStatus.WORKING else state.status
        final_output = state.final_output
        output: str | None
        if isinstance(final_output, str) or final_output is None:
            output = final_output
        else:
            output = str(final_output)
        return cls(
            trace_id=state.trace_id,
            status=status,
            output=output,
            final_state_ref=f"mem://{state.trace_id}/{state.step}",
            total_steps=state.step + 1,
            budget_used=state.budget,
            error=state.last_error,
        )


class ApprovalPendingError(Exception):
    """Agent 需要人工审批时抛出，暂停执行等待 HITL 决策。"""

    def __init__(self, approval_request: Any):
        self.approval_request = approval_request
        super().__init__("waiting for human approval")


class BudgetExceededError(Exception):
    """Budget 超限（步数 / token / 费用 / 墙钟）时抛出。"""

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


class UnregisteredActionError(ToolExecutionError):
    """Raised when an ``action_type`` has no registered handler.

    This is a deterministic error — retrying will not help because the
    action catalog simply does not contain the requested type.
    """

    retryable = False

    def __init__(self, action_type: str):
        self.action_type = action_type
        super().__init__(f"未注册的 action_type: {action_type}")
