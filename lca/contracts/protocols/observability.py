"""可观测性协议 —— 业务层唯一发射门面。

业务层（L1-L3）只依赖本契约；后端（console/jsonl/langfuse）、传输骨干
（OpenTelemetry）全部被 L0 子系统封装，对本协议不可见。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Telemetry(Protocol):
    """应用发射门面：span / event / score，不耦合任何后端实现。

    - ``span``：打开一个命名 span（context manager），返回可变句柄；
    - ``event``：在当前 span 上记录一个业务事件（不可变事实）；
    - ``score``：对当前 span/trace 附加评估分数（后端不支持时降级为事件）。
    """

    def span(self, name: str, **attributes: Any) -> Any:
        """Context manager，yield 可变句柄（attributes 可中途写入）。"""
        ...

    def event(self, name: str, **attributes: Any) -> None:
        """记录业务事件；name 必须取自 contracts.telemetry.EventName。"""
        ...

    def score(self, name: str, value: float, **attributes: Any) -> None:
        """附加评估分数；无后端支持时降级为 span 事件。"""
        ...


@runtime_checkable
class ObservabilityBackend(Protocol):
    """装配完成的可观测后端的结构契约（门面身份 + 生命周期）。

    L0 的 ``BoundObservability`` 结构化满足本协议；声明式 spec 用它表达
    「字符串选择 | 已装配实例」双模，contracts 不依赖任何实现层。
    """

    def flush(self) -> None:
        """冲刷所有导出缓冲。"""
        ...

    def close(self) -> None:
        """冲刷并关闭全部后端。"""
        ...
