"""一次调用的元数据 —— 跨 AgentEntrypoint / TeamEntrypoint 统一透传。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InvocationContext:
    """一次调用的元数据。

    取代原先隐式的 ``**context: str``（任意 kwarg、无编译期保证）。
    ``extra`` 为显式逃生舱，供扩展字段使用。
    """

    trace_id: str | None = None
    delegated_by: str = ""
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)
