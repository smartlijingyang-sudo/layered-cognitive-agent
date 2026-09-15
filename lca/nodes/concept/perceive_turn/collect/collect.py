"""phase.concept.perceive_turn.perceive_input_collect — typed run_input collector.

``concept.perceive.turn`` 内嵌节点 1:typed ``run_input | None`` →
``tuple[Any, ...]``(感知输入集合的 typed 投影)。

ADR-0220 §3.4 把 ``perceive.input.collect`` 列为 business-graph 节点;
本概念图把4 个 perceive 节点封装到一张 ``concept.perceive.turn`` 图内
(没有再细拆更多 concept 图 — 与 §3.3 "节点数 ≤ 4" 规则一致)。
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
class PerceiveInputCollectExecutor:
    """``concept.perceive.turn`` 节点 1:run_input → tuple[Any, ...]。"""

    semantic_name: str = "perceive.input.collect"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("run_input",)
    declared_outputs: tuple[PortName, ...] = ("raw_inputs",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """perceive.input.collect 入口。

        inputs 端口(yaml):run_input (object | None)
        outputs 端口(yaml):raw_inputs (tuple[Any, ...])
        """
        del context
        run_input = input.port_values.get("run_input")
        if run_input is None:
            return NodeOutput(port_values={"raw_inputs": ()})
        if isinstance(run_input, tuple):
            return NodeOutput(port_values={"raw_inputs": run_input})
        return NodeOutput(port_values={"raw_inputs": (run_input,)})


@plugin(
    id="phase.concept.perceive_turn.perceive_input_collect",
    Config=None,
    provides=("concept::perceive.input.collect",),
    requires=(),
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
                "phase_concept_perceive_turn_perceive_input_collect.checked",
                "phase_concept_perceive_turn_perceive_input_collect.served",
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
    executor = PerceiveInputCollectExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["PerceiveInputCollectExecutor", "setup"]
