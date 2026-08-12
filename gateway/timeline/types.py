"""Timeline 领域事件类型定义 — frozen dataclass 联合类型。

替代旧架构中的裸 dict[str, Any]，获得编译期类型检查。
所有 dataclass 共享 seq: int 和 type: str 字段，
mypy 通过 Union narrowing 做 exhaustiveness 检查。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class RunStartEvent:
    """Run 开始事件。"""

    seq: int = 0
    type: Literal["run.start"] = "run.start"
    run_id: str = ""
    trace_id: str = ""
    objective_preview: str = ""


@dataclass(frozen=True)
class ThinkingDeltaEvent:
    """思考过程增量事件。"""

    seq: int = 0
    type: Literal["thinking.delta"] = "thinking.delta"
    step: int = 0
    text: str = ""


@dataclass(frozen=True)
class ThinkingEndEvent:
    """思考过程结束事件。"""

    seq: int = 0
    type: Literal["thinking.end"] = "thinking.end"
    step: int = 0
    content: str = ""
    duration_ms: int = 0


@dataclass(frozen=True)
class AnswerDeltaEvent:
    """答案增量事件。"""

    seq: int = 0
    type: Literal["answer.delta"] = "answer.delta"
    step: int = 0
    text: str = ""


@dataclass(frozen=True)
class ToolStartEvent:
    """工具调用开始事件。"""

    seq: int = 0
    type: Literal["tool.start"] = "tool.start"
    tool_call_id: str = ""
    tool_name: str = ""  # LCA 内部名，如 "execute_code"
    arguments: dict[str, Any] = field(default_factory=dict)
    plugin_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolDeltaEvent:
    """工具执行增量输出事件。"""

    seq: int = 0
    type: Literal["tool.delta"] = "tool.delta"
    tool_call_id: str = ""
    stream: str = "stdout"
    text: str = ""
    plugin_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolEndEvent:
    """工具调用结束事件。"""

    seq: int = 0
    type: Literal["tool.end"] = "tool.end"
    tool_call_id: str = ""
    tool_name: str = ""
    ok: bool = True
    content: str = ""
    plugin_state: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    error: str = ""
    files: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RunEndEvent:
    """Run 结束事件。"""

    seq: int = 0
    type: Literal["run.end"] = "run.end"
    status: str = "completed"
    steps: int = 0
    output: str = ""
    error: str = ""


# 联合类型（用于类型标注和 match/case exhaustiveness checking）
TimelineEvent = (
    RunStartEvent
    | ThinkingDeltaEvent
    | ThinkingEndEvent
    | AnswerDeltaEvent
    | ToolStartEvent
    | ToolDeltaEvent
    | ToolEndEvent
    | RunEndEvent
)
