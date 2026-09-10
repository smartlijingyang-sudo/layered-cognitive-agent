"""NodeContext 工厂 (ADR-0218 §3.3 Adapter)。

职责:framework ↔ plugin 适配层,**只**做一件事——把 scope + yaml node +
outer state 投影成 plugin 看到的 NodeContext。

D5 消费点:NodeGraphDriver.run() 主循环每轮调一次。

边界:
- 不感知 executor 签名
- 不调 factory_resolver — Cordis resolution happens earlier in the stack (SubgraphRunner / node_graph_driver)
- 不读 yaml(除 `node.config` 直接传 budget)
- 用 MappingProxyType 包 budget/metadata 防止 plugin 修改 framework 内部状态
- scope 是 MappingRestrictedScope(capability by .resolve(key)),**不**是 dict
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping, Protocol


class _ScopeLike(Protocol):
    """最小 scope 接口——任何有 .resolve(capability) 的对象都可注入。"""

    def resolve(self, capability: str) -> Any: ...


from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphNode,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
)


class NodeRuntimeView:
    """NodeContext.runtime 投影。

    把 cordis scope 的 capability 动态投影为属性访问,**字段语义对齐 yaml 中
    各节点的 runtime[...] 读取**(参见 ADR-0218 §3.3)。

    属性通过 ``scope.resolve(key)`` 动态解析,无硬编码字段名。
    ``state`` 是特例——直接持有 outer AgentState,不经 scope。

    framework 不强制 capability 存在;plugin 自己 None 检查。
    """

    __slots__ = ("_state", "_scope")

    def __init__(
        self,
        *,
        state: AgentState,
        scope: _ScopeLike,
    ) -> None:
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_scope", scope)

    @property
    def state(self) -> AgentState:
        return self._state

    def __getattr__(self, key: str) -> Any | None:
        """Dynamic capability resolution from Cordis scope."""
        try:
            return self._scope.resolve(key)
        except (KeyError, AttributeError, TypeError):
            return None

    def __setattr__(self, key: str, value: Any) -> None:
        raise AttributeError("NodeRuntimeView is read-only")


def build_node_context(
    *,
    node: BundleGraphNode,
    plan_ref: str,
    outer_state: AgentState,
    scope: _ScopeLike,
) -> NodeContext:
    """构造 NodeContext。

    `scope` 是 framework 注入的 capability scope(满足 ``.resolve(key) -> obj``
    接口的对象,通常 ``MappingRestrictedScope``)。NodeRuntimeView 通过
    ``__getattr__`` 动态解析 capability,无硬编码字段名。

    `budget` / `metadata` 用 MappingProxyType 包,frozen view(plugin 只读)。
    """
    runtime = NodeRuntimeView(state=outer_state, scope=scope)

    # budget: yaml node.config 直接当 budget;plugin 读 budget["max_visits"] 等
    budget_view = MappingProxyType(dict(node.config))

    # metadata: 节点 + plan + 用途
    metadata_view = MappingProxyType(
        {
            "purpose": node.purpose,
            "plan_ref": plan_ref,
            "node_id": node.id,
            "node_region": node.region,
        }
    )

    return NodeContext(
        runtime=runtime,
        budget=budget_view,
        metadata=metadata_view,
    )


__all__ = [
    "NodeRuntimeView",
    "build_node_context",
]
