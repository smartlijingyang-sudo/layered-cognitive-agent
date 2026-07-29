"""跨层纯数据类型 —— 不承载业务协议，不依赖实现层。

与 protocols/ 的边界：这里只放 dataclass / 枚举别名；
任何带行为的 Protocol 不得出现在本文件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.lifecycle import TaskStatus


@dataclass
class Turn:
    """单步认知闭环的完整记录。

    让 Reasoner/Brain 在下一步能同时看到「上次怎么决策」与「发生了什么」。
    reflection 在 Critic.reflect 之前可为 None（两阶段写入）。
    """

    decision: StructuredDecision
    observation: Observation
    reflection: Reflection | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamAssignment:
    """团队级分工单元 —— 与单体内部计划项语义分离。

    - SubTask / 计划项：单体 Brain 内部的任务分解结果（不跨 Agent）
    - TeamAssignment：TeamEntrypoint / OrchestrationStrategy 对成员的分工
    """

    member_id: str
    objective: str
    depends_on: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepOutcome:
    """单步结果判定——Loop 唯一需要的"是否继续 + 如何收尾"信号。

    由 StepOutcomePolicy 产出，Loop 只消费结果，不参与推导。
    """

    should_stop: bool = False
    final_output: str | None = None
    status: TaskStatus | None = None
