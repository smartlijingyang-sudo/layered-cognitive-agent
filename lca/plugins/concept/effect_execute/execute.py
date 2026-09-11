"""phase.concept.effect_execute.effect_execute — typed effect dispatcher.

concept.effect.execute 图唯一节点 plugin:typed ``Decision`` +
``AgentState`` → ``EffectReceipt`` typed boundary (ADR-0220 §3.3 + §4.2)。

节点职责:把 typed ``Decision``(action_type / tool_calls / delegations /
response_text) dispatch 到对应 capability seam, 收集 typed
``EffectReceipt``。``body`` capability 从 ``runtime.body`` 读;缺失 →
RuntimeError(fail-loud)。RESPOND/DELEGATE 决策返回"skipped" receipt,
让 reflection graph 仍能记录"no effect attempted"的事实。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.ids.ids import new_id
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
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState
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
    """concept.effect.execute 节点:Decision → EffectReceipt。"""

    semantic_name: str = "effect.execute"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("decision", "state")
    declared_outputs: tuple[PortName, ...] = ("receipt",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """effect.execute 入口。

        inputs 端口(yaml):decision (Decision), state (AgentState)
        outputs 端口(yaml):receipt (EffectReceipt)
        """
        runtime = context.runtime
        decision = input.port_values.get("decision")
        state = input.port_values.get("state") or runtime.state

        if not isinstance(decision, Decision):
            raise TypeError(
                "effect.execute: 'decision' port must be a Decision instance, "
                f"got {type(decision).__name__}"
            )
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "effect.execute: 'state' port must be an AgentState "
                f"instance or None, got {type(state).__name__}"
            )

        receipt = _execute(decision, runtime)
        return NodeOutput(port_values={"receipt": receipt})


def _execute(decision: Decision, runtime: Any) -> EffectReceipt:
    """Dispatch the typed Decision into the body capability.

    RESPOND / DELEGATE → receipt 表示 skipped effect(没有 tool 调用),
    让 reflection 仍能记录。USE_TOOL → 调 ``runtime.body.dispatch_tool``
    typed seam;缺失 body → fail loud。
    """
    if decision.action_type == ActionType.RESPOND.value:
        return _skipped_receipt(provider="respond")
    if decision.action_type == ActionType.DELEGATE.value:
        return _skipped_receipt(provider="delegate")
    if decision.action_type != ActionType.USE_TOOL.value:
        return _skipped_receipt(provider=f"unknown:{decision.action_type}")

    if not decision.tool_calls:
        return _skipped_receipt(provider="use_tool_empty")

    body = getattr(runtime, "body", None)
    if body is None:
        raise RuntimeError(
            "effect.execute: 'body' capability missing from runtime scope — "
            "wire a Body dispatcher before concept.effect.execute runs."
        )

    first_call = decision.tool_calls[0]
    invocation_id = first_call.call_id or new_id("inv")
    idempotency_key = first_call.idempotency_key or new_id("idem")
    try:
        dispatch = getattr(body, "dispatch_tool", None)
        if not callable(dispatch):
            raise RuntimeError("effect.execute: runtime.body.dispatch_tool must be callable.")
        output_ref = dispatch(
            tool_name=first_call.tool_name,
            arguments=dict(first_call.arguments),
            invocation_id=invocation_id,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        return EffectReceipt(
            invocation_id=invocation_id,
            outcome=EffectOutcome.FAILED,
            idempotency_key=idempotency_key,
            provider=first_call.tool_name,
            error_code=type(exc).__name__,
            retryable=True,
        )
    output_str = output_ref if isinstance(output_ref, str) else None
    return EffectReceipt(
        invocation_id=invocation_id,
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key=idempotency_key,
        provider=first_call.tool_name,
        output_ref=output_str,
    )


def _skipped_receipt(*, provider: str) -> EffectReceipt:
    """A typed EffectReceipt that records "no effect was attempted"."""
    invocation_id = new_id("inv")
    return EffectReceipt(
        invocation_id=invocation_id,
        outcome=EffectOutcome.SUCCEEDED,
        idempotency_key=invocation_id,
        provider=provider,
        output_ref=None,
    )


@plugin(
    id="phase.concept.effect_execute.effect_execute",
    Config=None,
    provides=("concept::effect.execute",),
    requires=("body",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="tool",
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
                "phase_concept_effect_execute_effect_execute.checked",
                "phase_concept_effect_execute_effect_execute.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "body"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = EffectExecuteExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["EffectExecuteExecutor", "setup"]
