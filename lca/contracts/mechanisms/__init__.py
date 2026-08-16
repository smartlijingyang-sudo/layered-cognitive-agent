"""跨层机制契约 —— 不产生业务认知语义，只负责挂载 / 触发 / 查找。

边界判定（三者 vs 业务协议）：
- EventBus / Hook / HookRegistry：观察与横切副作用，不改变决策语义
- NamedRegistryProtocol / ComponentRegistryProtocol / TransportRegistryProtocol：按名解析实现，无业务规则
- SeamRole / SeamRegistry / seam：Capability Seam 三角色约束（DSH-inspired）
- 业务协议（Brain / Body / Memory / Runtime / Team…）→ 放 protocols/

protocols/ 包内不应再定义 Registry / EventBus / Hook 类。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar, runtime_checkable

from lca.contracts.mechanisms.capability import (
    REQUIRED_SEAM_KEYS as REQUIRED_SEAM_KEYS,
)
from lca.contracts.mechanisms.capability import (
    CapabilityContext as CapabilityContext,
)
from lca.contracts.mechanisms.capability import (
    MissingCapabilityError as MissingCapabilityError,
)
from lca.contracts.mechanisms.capability import (
    SeamKey as SeamKey,
)

# Re-export seam 三角色约束
from lca.contracts.mechanisms.seam import (
    IncompleteSeamError as IncompleteSeamError,
)
from lca.contracts.mechanisms.seam import (
    SeamDeclaration as SeamDeclaration,
)
from lca.contracts.mechanisms.seam import (
    SeamRegistry as SeamRegistry,
)
from lca.contracts.mechanisms.seam import (
    SeamRole as SeamRole,
)
from lca.contracts.mechanisms.seam import (
    UnauthorizedConsumerError as UnauthorizedConsumerError,
)
from lca.contracts.mechanisms.seam import (
    consume as consume,
)
from lca.contracts.mechanisms.seam import (
    get_global_seam_registry as get_global_seam_registry,
)
from lca.contracts.mechanisms.seam import (
    register_seam as register_seam,
)
from lca.contracts.mechanisms.seam import (
    require_complete as require_complete,
)
from lca.contracts.mechanisms.seam import (
    seam as seam,
)
from lca.contracts.mechanisms.seam import (
    validate_all_seams as validate_all_seams,
)
from lca.contracts.models.core.state import AgentState

T = TypeVar("T")


@runtime_checkable
class EventBus(Protocol):
    """事件总线：发布 / 订阅异步事件 + waterfall/serial 分发。

    - ``emit``：fire-and-forget 广播（观察者模式）
    - ``waterfall``：around-middleware 链（每个 listener 收到 (payload, next)）
    - ``serial``：串行决策链（每个 listener 收到 payload，返回新 payload）
    """

    def emit(self, event_name: str, payload: dict[str, Any], trace_id: str) -> None: ...
    def subscribe(
        self, event_name: str, handler: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None: ...
    async def drain(self) -> None:
        """等待已发射事件的订阅者全部处理完（run 收尾前调用，
        保证异步派发的桥接事件先于容器关闭落入 journal）。"""
        ...

    async def waterfall(self, event_name: str, initial: T) -> T:
        """Around-middleware 链：每个 listener 收到 (payload, next)。
        调用 next() 交给下一个 listener；不调用 = 短路。
        用于权限检查、策略拦截、Hook 链式调用。"""
        ...

    async def serial(self, event_name: str, initial: T) -> T:
        """串行决策链：每个 listener 收到 payload，返回新 payload。
        用于"最后一个 listener 说了算"的决策场景。"""
        ...


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
class OrchestrationRegistryProtocol(Protocol):
    """编排策略注册表接口：策略键 + TeamAssembly → 封闭 TeamStrategy。

    与 NamedRegistryProtocol（无参工厂）不同，编排工厂在 resolve 时接收
    组合期闭合的 TeamAssembly（governance / stage / lead），从中取所需
    闭合策略——所有治理方式（含 lead）走同一条注册表分发路径（ADR-0034）。
    """

    def register(self, name: str, impl: Any) -> None: ...

    def resolve(self, name: str, assembly: Any) -> Any: ...

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
