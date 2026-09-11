"""phase.concept.act_subgraph.act_envelope — typed envelope constructor.

``concept.act_subgraph`` 内嵌节点:``Decision`` → ``CommandEnvelope``。

从 ``StandardActExecutor`` (lca/plugins/loop/phase/act/standard/plugin.py
lines 50-75) 提取信封构造逻辑,作为 act 子图的独立概念节点。
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
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.act.command.envelope import (
    CapabilityGrant,
    CommandEnvelope,
    mint_envelope,
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
class ActEnvelopeExecutor:
    """``concept.act_subgraph`` 节点:Decision → CommandEnvelope。"""

    semantic_name: str = "act.envelope"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("decision",)
    declared_outputs: tuple[PortName, ...] = ("envelope",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.envelope 入口。

        inputs 端口(yaml): decision (Decision)
        outputs 端口(yaml): envelope (CommandEnvelope)
        """
        decision = input.port_values.get("decision")
        if not isinstance(decision, Decision):
            raise TypeError(
                "act.envelope: 'decision' port must be a Decision "
                f"instance, got {type(decision).__name__}"
            )

        plan_ref = context.metadata["plan_ref"]
        node_ref = context.metadata["node_id"]

        envelope: CommandEnvelope = mint_envelope(
            plan_ref=plan_ref,
            scope_ref=node_ref,
            decision=decision,
            provider="effect.body",
            grant=CapabilityGrant(
                capability="body.act",
                scope="run",
                effect_class="tools",
            ),
            idempotency_key=f"{plan_ref}:{node_ref}:{decision.decision_id}",
            metadata={
                "effect_class": "tools",
                "operation": "body.act",
                "state": context.runtime.state,
                "decision": decision,
            },
        )

        return NodeOutput(port_values={"envelope": envelope})


@plugin(
    id="phase.concept.act_subgraph.act_envelope",
    Config=None,
    provides=("concept::act.envelope",),
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
                "phase_concept_act_subgraph_act_envelope.checked",
                "phase_concept_act_subgraph_act_envelope.served",
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
    executor = ActEnvelopeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActEnvelopeExecutor", "setup"]
