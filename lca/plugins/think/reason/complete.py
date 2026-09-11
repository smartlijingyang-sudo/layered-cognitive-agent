"""phase.think.reason.complete — invoke LLM once per turn.

think.reason inner_graph 第 3 节点 plugin:调 ``Reasoner.complete_turn``
从 (state, render) 拿 LLMResponse,本图唯一调 LLM 节点。``requires=("reasoner",)``
通过 Cordis 校验,运行时从 ``context.runtime.reasoner`` 拿 capability 实例。

ADR-0218 §3.3:节点 plugin 由作者显式书写完整 ``@plugin(...)`` 装饰器,
工厂 ``setup(ctx)`` 通过 Cordis ``ctx.provide`` 单键注册 composite key。
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
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ThinkReasonCompleteExecutor:
    """think.reason inner_graph 第 3 节点:从 (state, render) 调 LLM 拿 LLMResponse。"""

    semantic_name: str = "think.reason.complete"
    region: str = "phase:think"
    # ADR-0219 §5.5: typed port contract declared on the plugin (graph
    # layer does not know port names; it only knows topology).
    declared_inputs: tuple[PortName, ...] = ("turn_render",)
    declared_outputs: tuple[PortName, ...] = ("response",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think.reason.complete 入口。

        inputs 端口(yaml):turn_render
        outputs 端口(yaml):response
        """
        import logging

        _log = logging.getLogger(__name__)
        runtime = context.runtime
        state = runtime.state
        reasoner = runtime.reasoner
        render = input.port_values.get("turn_render")

        if reasoner is None or state is None or render is None:
            raise RuntimeError(
                "think.reason.complete requires reasoner, state, and turn_render; "
                f"got reasoner={reasoner!r} state={state!r} render={render!r}"
            )
        complete_turn = getattr(reasoner, "complete_turn", None)
        if not callable(complete_turn):
            raise RuntimeError(
                f"think.reason.complete requires reasoner.complete_turn; "
                f"reasoner type {type(reasoner).__name__} lacks it"
            )
        # Tools are passed explicitly; fall back to reasoner's boot-time
        # tools if the runtime context doesn't provide per-turn tools.
        response = await complete_turn(state, render)
        _log.debug(
            "think.reason.complete response_type=%s",
            type(response).__name__,
        )
        return NodeOutput(port_values={"response": response})


@plugin(
    id="phase.think.reason.complete",
    Config=None,
    provides=("phase:think::think.reason.complete",),
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
                "phase_think_reason_complete.checked",
                "phase_think_reason_complete.served",
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
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = ThinkReasonCompleteExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ThinkReasonCompleteExecutor", "setup"]
