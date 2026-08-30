"""恢复输入在 carrier 与 Reducer 之间的纯数据契约。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lca.contracts.models.core.decision import Turn


@dataclass(frozen=True, slots=True)
class ResumeInput:
    """Reducer 折叠一次恢复所需的通用输入与可选历史记录。

    ``input_value`` 保留调用方提交的原始恢复值，供 Reducer 写入 working
    memory；``turn`` 则是具体交互渠道选择记录下来的可选历史事实。运行时只
    消费这个值，不需要知道它来自人工回复、审批系统还是自动恢复器。
    """

    input_value: object | None
    turn: Turn | None = None


class ResumeInputAdapter(Protocol):
    """把一个 carrier 输入收敛为可由 Reducer 折叠的恢复事实。"""

    def normalize(self, input_value: object | None) -> ResumeInput:
        """返回没有运行时策略泄漏的标准恢复输入。"""
        ...


class ResumeInputAdapterFactory(Protocol):
    """按 Agent 声明的键创建恢复输入适配器。"""

    def create(self, key: str) -> ResumeInputAdapter:
        """返回对应恢复语义的适配器，未知键时抛出 ``KeyError``。"""
        ...


__all__ = ["ResumeInput", "ResumeInputAdapter", "ResumeInputAdapterFactory"]
