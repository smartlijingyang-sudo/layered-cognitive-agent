"""phase.concept.stop_should_check.stop_focus_converge — typed StopPayload.

concept.stop.should_check 图节点 2:typed ``StopDecision`` + ``MemoryReceipt | None``
→ ``StopPayload`` typed boundary (ADR-0220 §3.3 + §4.2)。

节点职责:把 ``StopDecision`` + ``MemoryReceipt`` 投影成 ``StopPayload``
typed boundary。``focus_converged`` flag 由 admit 决策决定:``MemoryReceipt.admitted``
且 ``should_stop=True`` → ``focus_converged=True``,否则 ``False``。
``final_output_ref`` 由 ``MemoryReceipt.memory_ref``(若有)填入。
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
from lca.contracts.models.cognition.boundary import MemoryReceipt, StopPayload
from lca.contracts.models.core.policy.stop import StopDecision
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
class StopFocusConvergeExecutor:
    """concept.stop.should_check 节点 2:StopDecision + MemoryReceipt → StopPayload。"""

    semantic_name: str = "stop.focus.converge"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("stop_decision", "memory_receipt")
    declared_outputs: tuple[PortName, ...] = ("stop_payload",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """stop.focus.converge 入口。

        inputs 端口(yaml):stop_decision (StopDecision), memory_receipt (MemoryReceipt | None)
        outputs 端口(yaml):stop_payload (StopPayload)
        """
        del context
        stop_decision = input.port_values.get("stop_decision")
        memory_receipt = input.port_values.get("memory_receipt")

        if not isinstance(stop_decision, StopDecision):
            raise TypeError(
                "stop.focus.converge: 'stop_decision' port must be a "
                f"StopDecision instance, got {type(stop_decision).__name__}"
            )
        if memory_receipt is not None and not isinstance(memory_receipt, MemoryReceipt):
            raise TypeError(
                "stop.focus.converge: 'memory_receipt' port must be a "
                f"MemoryReceipt or None, got {type(memory_receipt).__name__}"
            )

        payload = _converge(stop_decision, memory_receipt)
        return NodeOutput(port_values={"stop_payload": payload})


def _converge(
    stop_decision: StopDecision,
    memory_receipt: MemoryReceipt | None,
) -> StopPayload:
    """Project the StopDecision + MemoryReceipt onto the typed StopPayload boundary.

    Pure typed transformation. ``focus_converged`` semantics: if a
    reflection was admitted this turn (memory_receipt.admitted) AND
    the stop decision says continue, the agent has not yet converged;
    if stop should happen AND a memory ref was produced, the focus
    has converged into a durable artifact.
    """
    admitted = memory_receipt is not None and memory_receipt.admitted
    final_output_ref = memory_receipt.memory_ref if admitted else None
    focus_converged = stop_decision.should_stop and admitted

    reason_str = stop_decision.reason.value if stop_decision.reason else None
    return StopPayload(
        should_stop=stop_decision.should_stop,
        focus_converged=focus_converged,
        reason=reason_str,
        final_output_ref=final_output_ref,
    )


@plugin(
    id="phase.concept.stop_should_check.stop_focus_converge",
    Config=None,
    provides=("concept::stop.focus.converge",),
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
                "phase_concept_stop_should_check_stop_focus_converge.checked",
                "phase_concept_stop_should_check_stop_focus_converge.served",
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
    executor = StopFocusConvergeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["StopFocusConvergeExecutor", "_converge", "setup"]
