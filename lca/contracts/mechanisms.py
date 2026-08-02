"""跨层机制契约 —— 不产生业务认知语义，只负责挂载 / 触发 / 查找。

边界判定（三者 vs 业务协议）：
- EventBus / Hook / HookRegistry：观察与横切副作用，不改变决策语义
- NamedRegistryProtocol / ComponentRegistryProtocol / TransportRegistryProtocol：按名解析实现，无业务规则
- 业务协议（Brain / Body / Memory / Runtime / Team…）→ 放 protocols/

protocols/ 包内不应再定义 Registry / EventBus / Hook 类。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from lca.contracts.state import AgentState


@runtime_checkable
class EventBus(Protocol):
    """事件总线：发布 / 订阅异步事件。"""

    def emit(self, event_name: str, payload: dict[str, Any], trace_id: str) -> None: ...
    def subscribe(
        self, event_name: str, handler: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None: ...


@runtime_checkable
class Hook(Protocol):
    """生命周期钩子：接收事件名 + 当前状态，执行横切副作用。"""

    async def __call__(self, event_name: str, state: AgentState, **kwargs: Any) -> None: ...


@runtime_checkable
class HookRegistry(Protocol):
    """钩子注册表：按事件名注册和触发 Hook。"""

    def register(self, event_name: str, hook: Hook) -> None: ...
    async def trigger(self, event_name: str, state: AgentState, **kwargs: Any) -> None: ...


@runtime_checkable
class NamedRegistryProtocol(Protocol):
    """按名称注册和解析实体的通用注册表接口。

    具体实现（如 NamedRegistry）在 layer0 提供，
    消费方依赖此 Protocol 进行跨层解耦。
    """

    def register(self, name: str, impl: Any) -> None: ...

    def resolve(self, name: str) -> Any: ...

    def list(self) -> list[str]: ...

    def __contains__(self, name: str) -> bool: ...


@runtime_checkable
class ComponentRegistryProtocol(Protocol):
    """按 (category, name) 注册和解析组件实现的通用接口。

    与 NamedRegistryProtocol 的区别：键是二元组 (category, name)，
    对应发现型组件（memory / observability / state_store / decision_gate 等）
    按类别分组管理的场景。具体实现（如 ComponentRegistry）在 layer0 提供。
    """

    def register(self, category: str, name: str, impl: Any) -> None: ...
    def get(self, category: str, name: str) -> Any | None: ...
    def require(self, category: str, name: str) -> Any: ...
    def list(self, category: str) -> list[str]: ...
