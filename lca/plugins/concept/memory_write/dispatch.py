"""phase.concept.memory_write.memory_write_dispatch — typed MemorySystem write.

concept.memory.write 图节点 2:typed ``MemoryReceipt`` (with admit
decision) + ``Reflection`` + ``Observation`` + ``AgentState`` →
``MemoryReceipt`` (with ``memory_ref`` populated)(ADR-0220 §3.3 + §4.2)。

节点职责:admit=True → 调 ``MemorySystem.update(state, observation,
reflection)``,填充 ``memory_ref = new_id("mem")``;admit=False →
透传 receipt(rejection_reason 由 upstream admit-policy 节点决定)。
"""

from __future__ import annotations

from dataclasses import replace

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.cognition.boundary import MemoryReceipt
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.memory.memory import MemorySystem
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class MemoryWriteDispatchExecutor:
    """concept.memory.write 节点 2:admit + write → MemoryReceipt。"""

    semantic_name = "memory.write.dispatch"
    region = "concept"
    declared_inputs = ("memory_receipt", "observation", "reflection", "state")
    declared_outputs = ("memory_receipt",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """memory.write.dispatch 入口。

        inputs 端口(yaml):memory_receipt (MemoryReceipt), observation (Observation),
        reflection (Reflection), state (AgentState)
        outputs 端口(yaml):memory_receipt (MemoryReceipt,可能填 memory_ref)
        """
        runtime_obj = context.runtime
        receipt = input.port_values.get("memory_receipt")
        observation = input.port_values.get("observation")
        reflection = input.port_values.get("reflection")
        state = input.port_values.get("state") or runtime_obj.state

        if not isinstance(receipt, MemoryReceipt):
            raise TypeError(
                "memory.write.dispatch: 'memory_receipt' port must be a "
                f"MemoryReceipt instance, got {type(receipt).__name__}"
            )
        if not isinstance(observation, Observation):
            raise TypeError(
                "memory.write.dispatch: 'observation' port must be an "
                f"Observation instance, got {type(observation).__name__}"
            )
        if not isinstance(reflection, Reflection):
            raise TypeError(
                "memory.write.dispatch: 'reflection' port must be a "
                f"Reflection instance, got {type(reflection).__name__}"
            )
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "memory.write.dispatch: 'state' port must be an AgentState "
                f"instance or None, got {type(state).__name__}"
            )

        if not receipt.admitted or state is None:
            return NodeOutput(port_values={"memory_receipt": receipt})

        memory = _resolve_memory(runtime_obj)
        await memory.update(state, observation, reflection)
        stamped = replace(receipt, memory_ref=new_id("mem"))
        return NodeOutput(port_values={"memory_receipt": stamped})


def _resolve_memory(runtime_obj) -> MemorySystem:
    """Resolve the MemorySystem capability from runtime context."""
    memory = getattr(runtime_obj, "memory", None)
    if not isinstance(memory, MemorySystem):
        raise RuntimeError(
            "memory.write.dispatch: 'memory' capability missing from runtime "
            "scope — wire a MemorySystem provider before concept.memory.write "
            "runs (the default MemoryService is published under 'memory')."
        )
    return memory


@plugin(
    id="phase.concept.memory_write.memory_write_dispatch",
    Config=None,
    provides=("concept::memory.write.dispatch",),
    requires=("memory",),
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
                "phase_concept_memory_write_memory_write_dispatch.checked",
                "phase_concept_memory_write_memory_write_dispatch.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "memory"),
        emits=("plugin.served"),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = MemoryWriteDispatchExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["MemoryWriteDispatchExecutor", "setup"]
