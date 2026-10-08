"""phase.concept.act_subgraph.act_envelope — typed envelope constructor.

``concept.act_subgraph`` 内嵌节点:``Decision`` → ``tuple[CommandEnvelope, ...]``。

PR-3 (G-20, ADR-0232): a single ``Decision`` carrying ``N``
``tool_calls`` produces ``N`` envelopes, one per call.  The legacy
``envelope`` single-value port is preserved as a back-compat alias for
the first envelope (``envelopes[0]``) so downstream consumers that
have not yet been upgraded to read ``envelopes`` keep working.  When
``decision.tool_calls`` is empty the node produces an empty tuple and
an ``envelope=None`` pass-through — matching the pre-PR-3 contract.

ADR-0219 §5.5 typed-port contract: ``declared_inputs`` /
``declared_outputs`` are compile-time closed sets; this node writes
``envelopes`` (tuple) and ``envelope`` (single) and reads ``decision``
only.  No Body / Registry / SafeExecutor calls — execution narrow
door (AGENTS.md §3 C10) is held by ``effect.execute → Body →
SafeExecutor → Sandbox``.
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
    ToolsEnvelopeMeta,
    idempotency_key_for,
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
    """``concept.act_subgraph`` 节点:Decision → tuple[CommandEnvelope, ...]。

    One ``Decision.tool_calls[i]`` ⇒ one ``CommandEnvelope``.  Idempotency
    key includes the call index so a retry of the same decision does
    not collide envelopes from different calls in the same batch.
    """

    semantic_name: str = "act.envelope"
    region: str = "act"
    declared_inputs: tuple[PortName, ...] = (PortName("decision"), PortName("state"))
    # YAML ``outputs`` declares ``envelope, decision, state`` (ADR-0235 / PR-5
    # typed-port passthrough: state / decision carry into the dispatch chain
    # via the kernel-wide port registry). The executor must actually emit
    # those ports — otherwise the interpreter's ``setdefault(name, None)``
    # contract enforcement clears the carry-in ``decision`` port to None at
    # this visit, which breaks the outer act→think re-ask edge predicate
    # ``decision.action_type == use_tool`` and yields a silent H6 failure
    # (class: 2026-09-16-act-think-reask-loop-guard §"yaml executor mismatch").
    declared_outputs: tuple[PortName, ...] = (
        PortName("envelopes"),
        PortName("envelope"),
        PortName("decision"),
        PortName("state"),
    )

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.envelope 入口。

        inputs 端口(yaml): decision (Decision)
        outputs 端口(yaml): envelopes (tuple[CommandEnvelope, ...]),
                            envelope (CommandEnvelope | None — back-compat)
        """
        decision = input.port_values.get(PortName("decision"))
        if not isinstance(decision, Decision):
            raise TypeError(
                "act.envelope: 'decision' port must be a Decision "
                f"instance, got {type(decision).__name__}"
            )

        plan_ref = context.metadata["plan_ref"]
        node_ref = context.metadata["node_id"]

        if decision.delegations and not decision.tool_calls:
            envelopes = tuple(
                mint_envelope(
                    plan_ref=plan_ref,
                    scope_ref=node_ref,
                    decision=decision,
                    provider="effect.body",
                    grant=CapabilityGrant(
                        capability="body.act",
                        scope="run",
                        effect_class="delegations",
                    ),
                    idempotency_key=idempotency_key_for(
                        plan_ref=plan_ref,
                        scope_ref=node_ref,
                        decision_id=decision.decision_id,
                        discriminator=del_index,
                    ),
                    # RA-033: metadata 经 ToolsEnvelopeMeta 类型化 seam 构造；
                    # 活对象（state / decision）不再塞进 metadata —— handler
                    # 经 EffectHandler.handle 的 typed kwargs 拿对象。
                    metadata=ToolsEnvelopeMeta(
                        effect_class="delegations",
                        operation="body.act",
                        delegation_index=del_index,
                        decision_ref=decision.decision_id,
                    ).to_metadata(),
                )
                for del_index in range(len(decision.delegations))
            )
        else:
            envelopes = tuple(
                mint_envelope(
                    plan_ref=plan_ref,
                    scope_ref=node_ref,
                    decision=decision,
                    provider="effect.body",
                    grant=CapabilityGrant(
                        capability="body.act",
                        scope="run",
                        effect_class="tools",
                    ),
                    # Idempotency key includes the call index so a multi-call
                    # decision does not collapse N envelopes into one cached
                    # entry (PR-2 already separated BodySurfaceEventContract;
                    # this is the matching envelope-side guard).
                    idempotency_key=idempotency_key_for(
                        plan_ref=plan_ref,
                        scope_ref=node_ref,
                        decision_id=decision.decision_id,
                        discriminator=call_index,
                    ),
                    # RA-033: metadata 经 ToolsEnvelopeMeta 类型化 seam 构造。
                    # The dispatch site is the only place that knows which
                    # declared call this envelope carries. ``effect.execute``
                    # reads this id (via ``tools_meta_of``) to attribute the
                    # model-visible ``surface/tool_result`` row; reconstructing
                    # it downstream from ``decision`` only works for a
                    # single-call turn.
                    metadata=ToolsEnvelopeMeta(
                        effect_class="tools",
                        operation="body.act",
                        tool_call_id=tool_call.call_id,
                        tool_call_index=call_index,
                        decision_ref=decision.decision_id,
                    ).to_metadata(),
                )
                for call_index, tool_call in enumerate(decision.tool_calls)
            )

        return NodeOutput(
            port_values={
                PortName("envelopes"): envelopes,
                # Back-compat: downstream 1:1 wiring reads ``envelope``;
                # populate it with the first envelope (or None).
                PortName("envelope"): envelopes[0] if envelopes else None,
                # ADR-0235 / PR-5: state / decision carry through into the
                # dispatch chain as typed ports. Without these passthroughs,
                # ``interpreter.setdefault(name, None)`` clears the carry-in
                # ``decision`` here, and the outer act→think re-ask edge's
                # ``decision.action_type`` predicate fails on the next hop.
                PortName("decision"): decision,
                PortName("state"): input.port_values.get(PortName("state")),
            }
        )


@plugin(
    id="phase.concept.act_subgraph.act_envelope",
    Config=None,
    provides=("act::act.envelope",),
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
