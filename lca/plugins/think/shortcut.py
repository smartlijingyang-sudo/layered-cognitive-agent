"""phase.think.shortcut — try a deterministic shortcut before reason.

think 子图节点 plugin:在 LLM 推理之前尝试确定性快速路径。
``requires=("supports_shortcut",)`` 通过 Cordis 校验,
运行时从 ``context.runtime.supports_shortcut`` 拿 capability 实例。

ADR-0218 §3.3:节点 plugin 由作者显式书写完整 ``@plugin(...)`` 装饰器,
工厂 ``setup(ctx)`` 同时做 Cordis ``ctx.provide`` 与
``FactoryRegistry.register``(think 子图专用的 NodeExecutor 解析)。
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
from lca.contracts.protocols.declarative.declarative_1.factory_resolver import (
    get_default_registry,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.think.cognition import SupportsShortcut
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_SEMANTIC_NAME = "think.shortcut"
_REGION = "phase:think"


@dataclass(frozen=True, slots=True)
class ThinkShortcutExecutor:
    """think 节点:在 LLM 推理前调用 SupportsShortcut.try_shortcut。"""

    semantic_name: str = _SEMANTIC_NAME

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口(yaml):in_assembled_manifest
        outputs 端口(yaml):decision
        """
        runtime = context.runtime
        state = runtime.state
        cap = runtime.supports_shortcut

        if cap is None or state is None:
            return NodeOutput(port_values={})

        assert isinstance(cap, SupportsShortcut), (  # noqa: S101
            "think.shortcut runtime.supports_shortcut must implement SupportsShortcut"
        )
        decision = await cap.try_shortcut(state)
        if decision is None:
            return NodeOutput(port_values={})
        return NodeOutput(port_values={"decision": decision})


@plugin(
    id="phase.think.shortcut",
    Config=None,
    provides=("phase.think.shortcut",),
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
                "phase_think_shortcut.checked",
                "phase_think_shortcut.served",
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
    """双注册:Cordis provide + FactoryRegistry register。"""
    del config
    executor = ThinkShortcutExecutor()
    ctx.provide("phase.think.shortcut", executor)
    get_default_registry().register(
        executor,
        semantic_name=_SEMANTIC_NAME,
        region=_REGION,
    )


__all__ = ["ThinkShortcutExecutor", "setup"]
