"""可观测性 port 契约 —— 业务层与 adapter 的解耦点（Hexagonal / Ports & Adapters）。

业务层只依赖这些 Protocol；adapter 实现不感知彼此；插件注册表按名字解析。
新增 backend = 新增 plugin + 注册到对应 seam，不动 facade。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Any, Protocol, runtime_checkable

from lca.contracts.models.observability.journal import JournalEvent, StampedEvent


@runtime_checkable
class JournalBackend(Protocol):
    """事实账本后端：业务层 ``record(event)`` 的唯一接收端。

    实现内部聚合 store（append-only 存储）+ projection registry（reader 扇出）
    + attribute policy（脱敏/截断）。业务层看不到这三个组件，只看到 ``write``。
    """

    def write(self, event: JournalEvent) -> StampedEvent | None:
        """提交一条领域/运行时事件；返回盖章后的记录或 None（未绑定时安全 no-op）。"""
        ...

    def flush(self) -> None: ...
    def close(self) -> None: ...


@runtime_checkable
class TracerBackend(Protocol):
    """外部追踪后端：``span(name)`` context manager 的实现端。

    adapter 持有 OTel SDK 的 ``Tracer`` 实例；policy 走独立 plugin，adapter 不感知。
    """

    def start(self, name: str, **attrs: Any) -> AbstractContextManager[Any]:
        """打开一个 span；返回 context manager，退出时落属性/结束 span。"""
        ...


@runtime_checkable
class ScorerBackend(Protocol):
    """评估后端：``score(name, value)`` 的接收端。"""

    def score(self, name: str, value: float, **attrs: Any) -> None: ...


# Scorer 就是 ``Callable[[str, float, dict], None]``；Protocol 仅用于类型标注。
ScorerFn = Callable[[str, float, dict[str, Any]], None]


@runtime_checkable
class AttributePolicyBackend(Protocol):
    """写入期属性策略：脱敏/截断/verbosity 的强制点。"""

    def prepare(self, attributes: dict[str, Any]) -> dict[str, Any]: ...


# 抑制 unused-import 警告（runtime_checkable 让 Protocol 运行时可被 isinstance 检查）
_ = (Iterator,)
