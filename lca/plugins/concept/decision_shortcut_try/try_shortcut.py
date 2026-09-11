"""phase.concept.decision_shortcut_try.shortcut_try — typed Decision shortcut.

concept.decision.shortcut_try 图唯一节点 plugin:typed ``AgentState``
→ ``Decision | None``(ADR-0220 §3.3)。

节点职责:在 LLM 推理之前尝试确定性快速路径,这是 ``SupportsShortcut``
Protocol 在概念图层的 typed 投影。返回 ``None`` 不算错误,是"这层定
不了,交给 LLM"的合法语义(对齐 ``SupportsShortcut.try_shortcut`` 的
``None`` 语义)。

``requires=("supports_shortcut",)`` 通过 Cordis 校验,运行时从
``context.runtime.supports_shortcut`` 拿 capability 实例(``SupportsShortcut``
duck-type Protocol,无需运行时强制 isinstance)。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.think.cognition import SupportsShortcut
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ShortcutTryExecutor:
    """concept.decision.shortcut_try 节点:state → Decision | None。"""

    semantic_name: str = "shortcut.try"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("state",)
    declared_outputs: tuple[PortName, ...] = ("decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """shortcut.try 入口。

        inputs 端口(yaml):state (AgentState)
        outputs 端口(yaml):decision (Decision | None)

        缺失 state 或 capability → 返回空 ports,让 driver 走下一次
        edge 选择(典型情况:production 的 ``business.reasoning.shortcut``
        命中 ``shortcut.try`` 返回 ``None`` → driver 顺 edge 走到
        ``business.reasoning.turn`` 走 LLM 完整路径)。
        """
        runtime = context.runtime
        state = input.port_values.get("state") or runtime.state
        if state is None or not isinstance(state, AgentState):
            return NodeOutput(port_values={})

        shortcut = getattr(runtime, "supports_shortcut", None)
        if not isinstance(shortcut, SupportsShortcut):
            return NodeOutput(port_values={})

        decision = await shortcut.try_shortcut(state)
        return NodeOutput(port_values={"decision": decision})


@plugin(
    id="phase.concept.decision_shortcut_try.shortcut_try",
    Config=None,
    provides=("concept::shortcut.try",),
    requires=("supports_shortcut",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_concept_decision_shortcut_try_shortcut_try.checked",
                "phase_concept_decision_shortcut_try_shortcut_try.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "supports_shortcut"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = ShortcutTryExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ShortcutTryExecutor", "setup"]
