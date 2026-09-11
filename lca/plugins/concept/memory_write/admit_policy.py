"""phase.concept.memory_write.memory_admit_policy — typed memory admission policy.

concept.memory.write 图节点 1:typed ``Reflection`` → ``MemoryReceipt``
typed boundary (ADR-0220 §3.3 + §4.2)。

节点职责:决定一个 ``Reflection`` 是否值得记入长期记忆。``reflection_id``
+ ``admitted`` + ``rejection_reason`` 三元组是 typed boundary output。
准入策略: Reflection 的 ``lesson`` 非空 → admitted; verdict ==
ReflectionVerdict.APPROVED → admitted; 其余 → rejected。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ReflectionVerdict
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
from lca.contracts.models.cognition.boundary import MemoryReceipt
from lca.contracts.models.core.execution.decision import Reflection
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
class MemoryAdmitPolicyExecutor:
    """concept.memory.write 节点 1:Reflection → MemoryReceipt(admit decision)。"""

    semantic_name: str = "memory.admit.policy"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("reflection",)
    declared_outputs: tuple[PortName, ...] = ("memory_receipt",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """memory.admit.policy 入口。

        inputs 端口(yaml):reflection (Reflection)
        outputs 端口(yaml):memory_receipt (MemoryReceipt)
        """
        del context
        reflection = input.port_values.get("reflection")
        if not isinstance(reflection, Reflection):
            raise TypeError(
                "memory.admit.policy: 'reflection' port must be a Reflection "
                f"instance, got {type(reflection).__name__}"
            )

        receipt = _admit(reflection)
        return NodeOutput(port_values={"memory_receipt": receipt})


def _admit(reflection: Reflection) -> MemoryReceipt:
    """Decide whether the reflection is durable.

    Pure typed decision; no I/O, no env reads, no LLM call. The
    ``memory.write.dispatch`` node that consumes this receipt reads the
    ``admitted`` flag to know whether to actually call
    ``MemorySystem.update``.
    """
    has_lesson = bool(reflection.lesson and reflection.lesson.strip())
    approved = reflection.verdict is ReflectionVerdict.APPROVED
    if has_lesson or approved:
        return MemoryReceipt(
            admitted=True,
            memory_ref=None,  # the write-dispatch node fills this in
            reflection_id=reflection.reflection_id,
            rejection_reason=None,
        )
    return MemoryReceipt(
        admitted=False,
        memory_ref=None,
        reflection_id=reflection.reflection_id,
        rejection_reason="reflection without lesson and not APPROVED verdict",
    )


@plugin(
    id="phase.concept.memory_write.memory_admit_policy",
    Config=None,
    provides=("concept::memory.admit.policy",),
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
                "phase_concept_memory_write_memory_admit_policy.checked",
                "phase_concept_memory_write_memory_admit_policy.served",
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
    executor = MemoryAdmitPolicyExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["MemoryAdmitPolicyExecutor", "_admit", "setup"]
