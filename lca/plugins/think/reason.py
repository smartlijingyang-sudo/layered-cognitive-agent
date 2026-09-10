"""phase.think.reason — call the LLM via Reasoner, emitting spine facts.

think 子图节点 plugin:调 Reasoner 生成候选 LLMResponse。
``requires=("reasoner",)`` 通过 Cordis 校验,
运行时从 ``context.runtime.reasoner`` 拿 capability 实例。

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
from lca.contracts.protocols.think.cognition import Reasoner
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.emit.cognitive.reasoner import run_reasoner_with_spine_facts

_SEMANTIC_NAME = "think.reason"
_REGION = "phase:think"


@dataclass(frozen=True, slots=True)
class ThinkReasonExecutor:
    """think 节点:调 Reasoner 生成候选 LLMResponse。"""

    semantic_name: str = _SEMANTIC_NAME

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口(yaml):messages, tools
        outputs 端口(yaml):response
        """
        runtime = context.runtime
        state = runtime.state
        reasoner = runtime.reasoner

        if reasoner is None or state is None:
            return NodeOutput(port_values={})

        assert isinstance(reasoner, Reasoner), (  # noqa: S101
            "think.reason runtime.reasoner must implement Reasoner"
        )
        response = await run_reasoner_with_spine_facts(reasoner, state)
        return NodeOutput(port_values={"response": response})


@plugin(
    id="phase.think.reason",
    Config=None,
    provides=("phase.think.reason",),
    requires=("reasoner",),
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
                "phase_think_reason.checked",
                "phase_think_reason.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "reasoner"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """双注册:Cordis provide + FactoryRegistry register。"""
    del config
    executor = ThinkReasonExecutor()
    ctx.provide("phase.think.reason", executor)
    get_default_registry().register(
        executor,
        semantic_name=_SEMANTIC_NAME,
        region=_REGION,
    )


__all__ = ["ThinkReasonExecutor", "setup"]
