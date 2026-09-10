"""NodeContext 工厂 (ADR-0218 §3.3 Adapter)。

职责:framework ↔ plugin 适配层,**只**做一件事——把 scope + yaml node +
outer state 投影成 plugin 看到的 NodeContext。

D5 消费点:NodeGraphDriver.run() 主循环每轮调一次。

边界:
- 不感知 executor 签名
- 不调 FactoryRegistry
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

    把 cordis scope 的 capability 平移到 dataclass 实例,**字段语义对齐 yaml 中
    各节点的 runtime[...] 读取**(参见 ADR-0218 §3.3)。

    字段:
      state            : AgentState(outer state, plugin 只读)
      reasoner         : Reasoner | None
      decision_gate    : DecisionGate | None
      decision_classifier: DecisionClassifier | None
      skill_router     : SkillRouter | None
      supports_shortcut: SupportsShortcut | None
      agent_gates      : DecisionGate | None(think.gate 专用)
      reducer          : Any | None(think.route 专用)

    framework 不强制所有字段存在;plugin 自己 isinstance 检查。
    """

    __slots__ = (
        "state",
        "reasoner",
        "decision_gate",
        "decision_classifier",
        "skill_router",
        "supports_shortcut",
        "agent_gates",
        "reducer",
    )

    def __init__(
        self,
        *,
        state: AgentState,
        reasoner: Any | None = None,
        decision_gate: Any | None = None,
        decision_classifier: Any | None = None,
        skill_router: Any | None = None,
        supports_shortcut: Any | None = None,
        agent_gates: Any | None = None,
        reducer: Any | None = None,
    ) -> None:
        self.state = state
        self.reasoner = reasoner
        self.decision_gate = decision_gate
        self.decision_classifier = decision_classifier
        self.skill_router = skill_router
        self.supports_shortcut = supports_shortcut
        self.agent_gates = agent_gates
        self.reducer = reducer


def build_node_context(
    *,
    node: BundleGraphNode,
    plan_ref: str,
    outer_state: AgentState,
    scope: _ScopeLike,
) -> NodeContext:
    """构造 NodeContext。

    `scope` 是 framework 注入的 capability scope(满足 ``.resolve(key) -> obj``
    接口的对象,通常 ``MappingRestrictedScope``)。每个 key 对应 NodeRuntimeView
    的一个字段。缺则 None(plugin 自己处理)。

    `budget` / `metadata` 用 MappingProxyType 包,frozen view(plugin 只读)。
    """
    def _try_resolve(key: str) -> Any | None:
        try:
            return scope.resolve(key)
        except (KeyError, AttributeError, TypeError):
            return None

    runtime = NodeRuntimeView(
        state=outer_state,
        reasoner=_try_resolve("reasoner"),
        decision_gate=_try_resolve("decision_gate"),
        decision_classifier=_try_resolve("decision_classifier"),
        skill_router=_try_resolve("skill_router"),
        supports_shortcut=_try_resolve("supports_shortcut"),
        agent_gates=_try_resolve("agent_gates"),
        reducer=_try_resolve("reducer"),
    )

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
