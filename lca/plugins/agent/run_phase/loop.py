"""phase.agent.run.phase.loop — typed StopPayload loop-back node.

``agent.run.phase`` 顶层 phase 图的 loop-back 节点:typed
``StopPayload`` 透传(typed passthrough)。

语义:driver 走到 ``loop.back`` 后,检查 ``stop_payload.should_stop`` —
True → driver 终止整个 graph (无 out-edge);False → driver 走 loop-back
edge 回到 ``perceive.turn`` 节点(本图 yaml 的 edges 部分未声明
loop-back edge — driver 自身用 StopPayload.should_stop 决定是否终止)。

节点职责:把 typed ``StopPayload`` 投影回 typed ``StopPayload``(无变换),
并保留 typed boundary 供 driver 检查。typed passthrough 比
``sub_spec_ref: bundles/business/run_phase.yaml`` 简单且无递归风险。
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
from lca.contracts.models.cognition.boundary import StopPayload
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
class RunPhaseLoopExecutor:
    """``agent.run.phase`` 顶层 loop-back 节点:StopPayload → StopPayload。"""

    semantic_name: str = "loop.back"
    region: str = "agent"
    declared_inputs: tuple[PortName, ...] = ("stop_payload",)
    declared_outputs: tuple[PortName, ...] = ("stop_payload",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """loop.back 入口。

        inputs 端口(yaml):stop_payload (StopPayload)
        outputs 端口(yaml):stop_payload (StopPayload)
        """
        del context
        stop_payload = input.port_values.get("stop_payload")
        if not isinstance(stop_payload, StopPayload):
            raise TypeError(
                "loop.back: 'stop_payload' port must be a StopPayload "
                f"instance, got {type(stop_payload).__name__}"
            )
        return NodeOutput(port_values={"stop_payload": stop_payload})


@plugin(
    id="phase.agent.run.phase.loop",
    Config=None,
    provides=("agent::loop.back",),
    requires=(),
    layer="L3",
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
                "phase_business_run_phase_loop.checked",
                "phase_business_run_phase_loop.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = RunPhaseLoopExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["RunPhaseLoopExecutor", "setup"]
