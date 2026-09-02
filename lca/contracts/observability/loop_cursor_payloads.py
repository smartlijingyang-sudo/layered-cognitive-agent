"""ADR-0169 D4:LoopCursor record_* 方法的 payload frozen dataclass。

关键:
- step_id 与 incarnation 不让业务路径填(由 cursor 注入,见 PR-7)
- system / tools / messages / manifest digest + path 由 ModelVisibleCapture 写(PR-12)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ThinkingRecord:
    content_digest: str
    content_path: str | None
    token_count: int | None
    thinking_kind: Literal["reasoning", "final_response", "compaction"]


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    args_digest: str
    args_payload_path: str | None
    call_seq: int  # cursor 内自增


@dataclass(frozen=True)
class ToolResultRecord:
    tool_name: str
    result_digest: str
    result_path: str | None
    outcome: Literal["ok", "failure", "timeout", "denied"]


@dataclass(frozen=True)
class RequestHeader:
    """cursor 注入 step_id / incarnation;业务路径不能填(ADR-0169 D4)。"""

    step_id: str
    incarnation: int
    reason: Literal["initial", "next_step", "series", "change", "inherited"]
    model: str
    system_digest: str
    system_path: str
    tools_digest: str
    tools_path: str
    messages_digest: str
    messages_path: str
    manifest_digest: str
    manifest_path: str
    inherited_from_step: str | None = None


__all__ = [
    "RequestHeader",
    "ThinkingRecord",
    "ToolCallRecord",
    "ToolResultRecord",
]
