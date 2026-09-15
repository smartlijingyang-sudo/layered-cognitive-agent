"""phase.concept.effect_execute.effect_execute — typed effect dispatcher.

concept.effect.execute 图唯一节点 plugin:typed ``CommandEnvelope`` →
``EffectReceipt`` typed boundary (ADR-0220 §3.3 + §4.2).

节点职责:把 typed ``CommandEnvelope`` dispatch 到 EffectDispatcher capability,
收集 typed ``EffectReceipt``。``effect_gateway`` capability 从
``runtime.effect_gateway`` 读;缺失 → RuntimeError(fail-loud)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from lca.cognition.body.emit.observation_surface import (
    observation_content,
    observation_error,
)
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
from lca.contracts.models.core.execution.decision import Decision, Observation
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

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EffectExecuteExecutor:
    """concept.effect.execute 节点:CommandEnvelope → EffectReceipt."""

    semantic_name: str = "effect.execute"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("envelope",)
    # PR-3.8.5 fix1: emit ``receipts`` (list-of-one) so the act subgraph's
    # ``act.join`` typed-boundary node (declared_inputs=("receipts",)) sees
    # the receipt via the kernel port registry. Previously emitted the
    # singular ``receipt`` which left ``receipts=None`` at join and every
    # act subgraph run terminated silently at join.
    declared_outputs: tuple[PortName, ...] = ("receipts",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """effect.execute 入口。

        inputs 端口:envelope (CommandEnvelope)
        outputs 端口:receipts (list[EffectReceipt], length 1)

        职责还包括把 Observation 以 ``surface/tool_result`` 追加到 Session。
        这是模型能看到工具结果的唯一途径:think 侧 ``llm.call`` 已经写了
        ``surface/assistant_message``,act 侧若不写对应 result,
        ``derive_messages`` 就还原不出 ``role=tool`` 行,模型会以为自己的
        工具调用没有得到回应而反复重发同一个调用。
        """
        envelope = input.port_values.get("envelope")
        if not isinstance(envelope, CommandEnvelope):
            raise TypeError(
                "effect.execute: 'envelope' port must be a CommandEnvelope "
                f"instance, got {type(envelope).__name__}"
            )

        receipt, observation = await _dispatch(envelope, context)
        _append_tool_result_surface(context, envelope, receipt, observation)
        return NodeOutput(port_values={"receipts": [receipt]})


def _resolve_writer(context: NodeContext) -> Any:
    """Read the run-scoped ``RunSessionWriter`` off ``context.runtime``.

    Mirrors ``llm.call``: ``writer`` is a kernel-injected runtime port, not
    a value produced by a graph predecessor. Returns ``None`` when the
    runtime is unbound (legacy harnesses, unit fixtures).
    """
    runtime = getattr(context, "runtime", None)
    if runtime is None:
        return None
    writer = getattr(runtime, "writer", None)
    if writer is None and hasattr(runtime, "get"):
        writer = runtime.get("writer")
    return writer


def _tool_call_id(envelope: CommandEnvelope, observation: Observation | None) -> str | None:
    """Resolve the OpenAI ``call_id`` this result answers.

    ``derive_messages`` orphan-drops any ``role=tool`` row whose
    ``tool_call_id`` was not declared by an earlier
    ``assistant.tool_calls[].id`` (the id ``llm.call`` writes). The
    envelope's ``idempotency_key`` is ``plan:node:decision_id`` and never
    matches that id space, so using it would append a row that is then
    silently dropped — reintroducing the same retry loop through a
    different door.
    """
    if observation is not None:
        obs_call_id = getattr(observation, "tool_call_id", None)
        if obs_call_id:
            return str(obs_call_id)
    decision = envelope.metadata.get("decision")
    if isinstance(decision, Decision) and len(decision.tool_calls) == 1:
        return decision.tool_calls[0].call_id
    # Multiple declared calls collapse to a single Observation on this
    # seam (per-call fan-out is the action registry's batch path), so no
    # id can be attributed without guessing.
    return None


def _append_tool_result_surface(
    context: NodeContext,
    envelope: CommandEnvelope,
    receipt: EffectReceipt,
    observation: Observation | None,
) -> None:
    """Append ``surface/tool_result`` so the next think turn can see the result.

    Best-effort by design: the side effect already happened, so a journal
    failure must not rewrite the receipt or roll back the tool. The
    failure is logged because an unappended result is exactly the
    invisible condition that made the model retry a tool call twenty
    times in ``run_5857095cb3e9``.
    """
    if observation is None:
        return
    writer = _resolve_writer(context)
    if writer is None:
        _log.debug(
            "effect.execute: no bound writer; tool result not surfaced (invocation_id=%s)",
            receipt.invocation_id,
        )
        return
    call_id = _tool_call_id(envelope, observation)
    if call_id is None:
        _log.warning(
            "effect.execute: cannot attribute tool result to a call_id; "
            "skipping surface append (invocation_id=%s)",
            receipt.invocation_id,
        )
        return
    state = getattr(context.runtime, "state", None)
    step = getattr(state, "step", 0) or 0
    try:
        writer.append_tool_result(
            turn=step,
            step=step,
            call_id=call_id,
            content=observation_content(observation),
            error=observation_error(observation),
            meta={
                "tool_name": receipt.provider,
                "outcome": receipt.outcome.value,
                "invocation_id": receipt.invocation_id,
            },
        )
    except Exception:
        _log.exception(
            "effect.execute: failed to append surface/tool_result (call_id=%s)",
            call_id,
        )


def _derive_outcome(
    result: object,
) -> tuple[EffectOutcome, str | None, str | None]:
    """Derive EffectOutcome, error_code, and failure_kind from the dispatch result.

    If the result is an Observation (or contains one as ``result``),
    read ``success`` to decide SUCCEEDED vs FAILED.  A failed Observation
    contributes its ``error`` field as the error_code and its
    ``extra[FAILURE_KIND]`` as the failure_kind tag (so the cognition
    seam can distinguish deterministic failures from transient
    retries without re-classifying the text).
    """
    from lca.contracts.atoms.semantic.keys import FAILURE_KIND
    from lca.contracts.models.core.execution.decision import Observation

    obs: object | None = None
    if isinstance(result, Observation):
        obs = result
    elif isinstance(result, dict):
        inner = result.get("result")
        if isinstance(inner, Observation):
            obs = inner
    if obs is not None and not obs.success:
        error_code = (obs.error or "tool_failed")[:128]
        failure_kind = None
        if isinstance(obs.extra, dict):
            tag = obs.extra.get(FAILURE_KIND)
            if isinstance(tag, str) and tag:
                failure_kind = tag
        return EffectOutcome.FAILED, error_code, failure_kind
    return EffectOutcome.SUCCEEDED, None, None


def _extract_observation(result: object) -> Observation | None:
    """Pull the executed :class:`Observation` out of a gateway result.

    The gateway returns either a raw ``Observation`` (single tool call) or
    a dict receipt whose ``result`` key holds one (idempotency-cached
    path). Returns ``None`` for anything else so callers fall back to the
    receipt's stringified ``output_ref`` rather than guessing a payload.
    """
    if isinstance(result, Observation):
        return result
    if isinstance(result, dict):
        inner = result.get("result")
        if isinstance(inner, Observation):
            return inner
    return None


async def _dispatch(
    envelope: CommandEnvelope, context: NodeContext
) -> tuple[EffectReceipt, Observation | None]:
    """Dispatch the CommandEnvelope through the EffectDispatcher capability.

    Returns the receipt plus the executed Observation (``None`` when the
    result is not an Observation, e.g. ``memory.update``'s dict receipt),
    so the node can project a model-visible ``surface/tool_result`` row
    without re-parsing the stringified ``output_ref``.
    """

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
        return (
            EffectReceipt(
                invocation_id=invocation_id,
                outcome=EffectOutcome.FAILED,
                idempotency_key=envelope.idempotency_key or "",
                provider=envelope.metadata.get("operation", "unknown"),
                error_code=type(exc).__name__,
                retryable=True,
            ),
            None,
        )

    # output may be a dict receipt or a raw Observation
    if isinstance(output, dict):
        result = output.get("result", output)
        invocation_id = output.get("invocation_id", envelope.idempotency_key or "unknown")
    else:
        result = output
        invocation_id = envelope.idempotency_key or "unknown"

    outcome, error_code, failure_kind = _derive_outcome(result)
    return (
        EffectReceipt(
            invocation_id=str(invocation_id),
            outcome=outcome,
            idempotency_key=envelope.idempotency_key or "",
            provider=envelope.metadata.get("operation", "unknown"),
            output_ref=str(result) if result is not None else None,
            error_code=error_code,
            failure_kind=failure_kind,
        ),
        _extract_observation(result),
    )


@plugin(
    id="phase.concept.effect_execute.effect_execute",
    Config=None,
    provides=("concept::effect.execute",),
    requires=(),
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
        reads=("plugin.serve",),
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
