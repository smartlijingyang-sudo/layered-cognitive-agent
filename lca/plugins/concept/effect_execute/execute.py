"""phase.concept.effect_execute.effect_execute — typed effect dispatcher.

concept.effect.execute 图唯一节点 plugin:typed ``CommandEnvelope`` →
``EffectReceipt`` typed boundary (ADR-0220 §3.3 + §4.2).

节点职责:把 typed ``CommandEnvelope`` dispatch 到 EffectDispatcher capability,
收集 typed ``EffectReceipt``。``effect_gateway`` capability 从
``runtime.effect_gateway`` 读;缺失 → RuntimeError(fail-loud)。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
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
from lca.contracts.protocols.act.command.envelope import CommandEnvelope
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
class EffectExecuteExecutor:
    """concept.effect.execute 节点:CommandEnvelope → EffectReceipt."""

    semantic_name: str = "effect.execute"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("envelope",)
    declared_outputs: tuple[PortName, ...] = ("receipt",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """effect.execute 入口。

        inputs 端口:envelope (CommandEnvelope)
        outputs 端口:receipt (EffectReceipt)
        """
        envelope = input.port_values.get("envelope")
        if not isinstance(envelope, CommandEnvelope):
            raise TypeError(
                "effect.execute: 'envelope' port must be a CommandEnvelope "
                f"instance, got {type(envelope).__name__}"
            )

        receipt = await _dispatch(envelope, context)
        return NodeOutput(port_values={"receipt": receipt})


async def _dispatch(envelope: CommandEnvelope, context: NodeContext) -> EffectReceipt:
    """Dispatch the CommandEnvelope through the EffectDispatcher capability."""
    runtime = context.runtime
    gateway = getattr(runtime, "effect_gateway", None)
    if gateway is None:
        raise RuntimeError(
            "effect.execute: 'effect_gateway' capability missing from runtime "
            "scope — wire an EffectDispatcher before concept.effect.execute runs."
        )

    # Build a minimal EffectPolicyPlan from envelope metadata.
    # The real policy comes from CompiledRunPlan; for concept-level dispatch
    # we trust the envelope's own grant as the policy source.
    from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
        EffectPolicyPlan,
    )

    policy = EffectPolicyPlan(
        allowed_effects=(envelope.grant.effect_class,),
        approval_required=(),
        idempotency_required=(),
    )

    try:
        output = await gateway.execute(envelope, policy)
    except Exception as exc:
        invocation_id = envelope.idempotency_key or "unknown"
        return EffectReceipt(
            invocation_id=invocation_id,
            outcome=EffectOutcome.FAILED,
            idempotency_key=envelope.idempotency_key or "",
            provider=envelope.metadata.get("operation", "unknown"),
            error_code=type(exc).__name__,
            retryable=True,
        )

    # output may be a dict receipt or a raw Observation
    if isinstance(output, dict):
        result = output.get("result", output)
        invocation_id = output.get("invocation_id", envelope.idempotency_key or "unknown")
    else:
        result = output
        invocation_id = envelope.idempotency_key or "unknown"

    return EffectReceipt(
        invocation_id=str(invocation_id),
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key=envelope.idempotency_key or "",
        provider=envelope.metadata.get("operation", "unknown"),
        output_ref=str(result) if result is not None else None,
    )


@plugin(
    id="phase.concept.effect_execute.effect_execute",
    Config=None,
    provides=("concept::effect.execute",),
    requires=("effect_gateway",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="tools",
    contract=PluginContract(
        identity=PluginIdentity(version="v2"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_concept_effect_execute_effect_execute.checked",
                "phase_concept_effect_execute_effect_execute.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "effect_gateway"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key registration: ``{region}::{semantic_name}``."""
    del config
    executor = EffectExecuteExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["EffectExecuteExecutor", "setup"]
