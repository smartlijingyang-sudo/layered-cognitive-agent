"""LoopJudge 协议 —— 循环终止的唯一裁判。

将原先散落在 _loop 方法内的 budget 检查、outcome 判定、状态转换
收敛为一个内聚的 Protocol。Loop 只消费 TerminationSignal，
不参与终止推导。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.state import TypedState


class TerminationReason(Enum):
    """循环终止原因。"""

    CONTINUE = "continue"
    BUDGET_EXCEEDED = "budget_exceeded"
    TASK_COMPLETED = "task_completed"
    ERROR = "error"


@dataclass(frozen=True)
class TerminationSignal:
    """LoopJudge 对单步的裁决 —— Loop 唯一需要的终止信号。"""

    should_stop: bool = False
    reason: TerminationReason = TerminationReason.CONTINUE
    final_output: str | None = None
    status: TaskStatus | None = None


@runtime_checkable
class LoopJudge(Protocol):
    """循环终止裁判：每步结束后被调用，返回是否终止及原因。"""

    def judge(
        self,
        state: TypedState,
        decision: StructuredDecision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> TerminationSignal: ...
