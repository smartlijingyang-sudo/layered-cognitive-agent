"""phase.concept.reflection_critique.reflect_observation_build — typed observation build.

concept.reflection.critique 图节点 1:typed ``EffectReceipt`` →
``Observation`` (ADR-0220 §3.3 + §4.2)。

节点职责:把 ``EffectReceipt`` typed boundary 投影成 ``Observation`` —
``Critic.critique(state, observation)`` 的 typed 输入。``Observation``
的 payload / error 字段由 ``EffectReceipt.outcome`` + ``error_code``
派生。本节点保持纯 typed 变换,不调任何 capability。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.act.effect_receipt import (
    EffectOutcome,
    EffectReceipt,
)
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import Observation
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
class ReflectObservationBuildExecutor:
    """concept.reflection.critique 节点 1:EffectReceipt → Observation。"""

    semantic_name: str = "reflect.observation.build"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("receipt",)
    declared_outputs: tuple[PortName, ...] = ("observation",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """reflect.observation.build 入口。

        inputs 端口(yaml):receipt (EffectReceipt)
        outputs 端口(yaml):observation (Observation)
        """
        del context
        receipt = input.port_values.get("receipt")
        if not isinstance(receipt, EffectReceipt):
            raise TypeError(
                "reflect.observation.build: 'receipt' port must be an "
                f"EffectReceipt instance, got {type(receipt).__name__}"
            )

        observation = _build_observation(receipt)
        return NodeOutput(port_values={"observation": observation})


def _build_observation(receipt: EffectReceipt) -> Observation:
    """Project the typed EffectReceipt boundary onto a critic-ready Observation.

    Pure typed transformation: no I/O, no env reads, no LLM call.
    EffectReceipt.outcome maps to Observation.success; error_code
    becomes Observation.error when present.
    """
    return Observation(
        observation_id=f"obs_{receipt.invocation_id}",
        success=receipt.outcome is EffectOutcome.SUCCEEDED,
        payload=receipt.output_ref,
        content_type=ContentType.TEXT,
        tool_call_id=receipt.invocation_id,
        error=receipt.error_code,
    )


@plugin(
    id="phase.concept.reflection_critique.reflect_observation_build",
    Config=None,
    provides=("concept::reflect.observation.build",),
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
                "phase_concept_reflection_critique_reflect_observation_build.checked",
                "phase_concept_reflection_critique_reflect_observation_build.served",
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
    executor = ReflectObservationBuildExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ReflectObservationBuildExecutor", "_build_observation", "setup"]
