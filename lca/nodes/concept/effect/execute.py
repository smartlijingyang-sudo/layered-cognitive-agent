"""phase.concept.effect_execute.effect_execute — typed effect dispatcher.

concept.effect.execute 图唯一节点 plugin:typed ``CommandEnvelope`` →
``EffectReceipt`` typed boundary (ADR-0220 §3.3 + §4.2).

节点职责:把 typed ``CommandEnvelope`` dispatch 到 EffectDispatcher capability,
收集 typed ``EffectReceipt``。``effect_gateway`` capability 从
``runtime.effect_gateway`` 读;缺失 → RuntimeError(fail-loud)。
"""

from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

from lca.cognition.body.emit.observation_surface import (
    observation_content,
    observation_error,
)
from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.atoms.semantic.keys import OBS_TOOL_RESULTS
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
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    decision_scope,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.act.command.envelope import CommandEnvelope, tools_meta_of
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
from lca.nodes._resolve import resolve_writer

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EffectExecuteExecutor:
    """concept.effect.execute 节点:CommandEnvelope → EffectReceipt."""

    semantic_name: str = "effect.execute"
    region: str = "concept"
    # ADR-0234 / PR-2: verdict_refs is now a typed-port input — produced
    # by ``effect.pre_dispatch.envelope_check`` and consumed (passthrough)
    # here so the subgraph keeps a typed binding for the 5-gate verdict
    # set without re-checking them at this node.
    # ADR-0235 / PR-5: decision / state flow in as typed ports; they are
    # passed to ``EffectDispatcher.execute(envelope, policy, *,
    # decision=..., state=...)`` instead of being smuggled via
    # ``envelope.metadata``.
    declared_inputs: tuple[PortName, ...] = (
        PortName("envelope"),
        PortName("verdict_refs"),
        PortName("decision"),
        PortName("state"),
    )
    # PR-3.8.5 fix1: emit ``receipts`` (list-of-one) so the act subgraph's
    # ``act.join`` typed-boundary node (declared_inputs=("receipts",)) sees
    # the receipt via the kernel port registry. Previously emitted the
    # singular ``receipt`` which left ``receipts=None`` at join and every
    # act subgraph run terminated silently at join.
    declared_outputs: tuple[PortName, ...] = (PortName("receipts"),)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """effect.execute 入口。

        inputs 端口:envelope (CommandEnvelope), verdict_refs (tuple[str, ...]),
        decision (Decision), state (AgentState)
        outputs 端口:receipts (list[EffectReceipt], length 1)

        职责还包括把 Observation 以 ``surface/tool_result`` 追加到 Session。
        这是模型能看到工具结果的唯一途径:think 侧 ``llm.persist`` 已经写了
        ``surface/assistant_message``,act 侧若不写对应 result,
        ``derive_messages`` 就还原不出 ``role=tool`` 行,模型会以为自己的
        工具调用没有得到回应而反复重发同一个调用。
        """
        envelope = input.port_values.get(PortName("envelope"))
        if not isinstance(envelope, CommandEnvelope):
            raise TypeError(
                "effect.execute: 'envelope' port must be a CommandEnvelope "
                f"instance, got {type(envelope).__name__}"
            )

        # ADR-0235 / PR-5: decision / state are typed-port inputs; they
        # flow into ``gateway.execute(envelope, policy, *, decision=...,
        # state=...)`` instead of being smuggled via ``envelope.metadata``.
        decision = input.port_values.get(PortName("decision"))
        state = input.port_values.get(PortName("state"))
        if state is None:
            # RA-033 removed the envelope.metadata smuggle path, but the act
            # subgraph never wired a ``state`` producer upstream of this node
            # (the outer think.main->act.main edge carries only ``decision``),
            # so the typed port arrives as None on real runs (todo-80).
            # Fall back to the kernel-injected runtime port - the same source
            # ``_append_tool_result_surface`` already reads for the step.
            # Only a real AgentState is accepted; anything else keeps the
            # previous None so legacy fixtures stay on the fail-loud path.
            runtime_state = getattr(context.runtime, "state", None)
            if isinstance(runtime_state, AgentState):
                state = runtime_state

        receipt, observation, dispatch_error = await _dispatch(envelope, context, decision, state)
        _append_tool_result_surface(
            context, envelope, receipt, observation, dispatch_error, decision=decision
        )
        return NodeOutput(port_values={PortName("receipts"): [receipt]})


class ToolResultAttributionError(RuntimeError):
    """An executed tool result cannot be attributed to a declared ``call_id``.

    Attribution is a contract, not a best effort: ``derive_messages``
    orphan-drops a ``role=tool`` row whose ``tool_call_id`` was not
    declared by an earlier ``assistant.tool_calls[].id``, so an
    unattributed result leaves the model staring at its own unanswered
    call and re-issuing it (``run_5857095cb3e9``, ``run_71456ce99914``).
    """


@dataclass(frozen=True, slots=True)
class _ToolResultRow:
    """One model-visible result: the declared ``call_id`` it answers."""

    call_id: str
    observation: Observation | None
    dispatch_error: str | None


def _batch_rows(observation: Observation | None) -> tuple[_ToolResultRow, ...]:
    """Read the batch executor's per-call packaging, when present.

    ``ToolBatchExecutor`` collapses N executed calls into one aggregate
    ``Observation`` but keeps the per-call facts in
    ``extra[OBS_TOOL_RESULTS]`` — one entry per declared call, each with
    its own ``call_id``. That is the only place where a multi-call turn's
    results stay separable, so it is the only source this seam reads.
    """
    if observation is None:
        return ()
    entries = (observation.extra or {}).get(OBS_TOOL_RESULTS)
    if not isinstance(entries, (list, tuple)) or not entries:
        return ()
    rows: list[_ToolResultRow] = []
    for entry in entries:
        call_id = entry.get("call_id") if isinstance(entry, dict) else None
        if not call_id:
            raise ToolResultAttributionError(
                f"effect.execute: {OBS_TOOL_RESULTS} entry without call_id: {entry!r}"
            )
        inner = entry.get("observation") if isinstance(entry, dict) else None
        rows.append(
            _ToolResultRow(
                call_id=str(call_id),
                observation=inner if isinstance(inner, Observation) else observation,
                dispatch_error=None,
            )
        )
    return tuple(rows)


def _owed_rows(
    envelope: CommandEnvelope,
    receipt: EffectReceipt,
    observation: Observation | None,
    dispatch_error: str | None,
    decision: Decision | None = None,
) -> tuple[_ToolResultRow, ...]:
    """Resolve every ``surface/tool_result`` row this dispatch owes the model.

    Total by construction: a batch yields one row per executed call, a
    single call yields one row attributed by the envelope's own
    ``tool_call_id`` (minted at the dispatch site), and a dispatch that
    raised still owes its call an error row. An empty tuple means the
    effect was not a tool call (``memory.update`` returns a dict receipt
    and no Observation), so nothing model-visible is owed.
    """
    rows = list(_batch_rows(observation))
    if rows:
        # If the batch observation is partial and missing some declared tool_calls,
        # fill in the missing calls so every declared call_id receives a response.
        if decision is not None and decision.tool_calls:
            covered_call_ids = {r.call_id for r in rows}
            for tc in decision.tool_calls:
                if tc.call_id not in covered_call_ids:
                    rows.append(
                        _ToolResultRow(
                            call_id=str(tc.call_id),
                            observation=None,
                            dispatch_error=dispatch_error
                            or f"batch call {tc.tool_name} missing result",
                        )
                    )
        return tuple(rows)

    # RA-033: metadata 契约经 ToolsEnvelopeMeta 类型化 seam 读取 —— 不再手写
    # metadata["tool_call_id"] / metadata["effect_class"] 字符串 key。
    meta = tools_meta_of(envelope)
    if meta.effect_class != "tools":
        return ()

    # If dispatch raised and decision declared calls: every declared call owes an error row.
    if dispatch_error is not None and decision is not None and decision.tool_calls:
        return tuple(
            _ToolResultRow(
                call_id=str(tc.call_id),
                observation=None,
                dispatch_error=dispatch_error,
            )
            for tc in decision.tool_calls
        )

    call_id = meta.tool_call_id or getattr(observation, "tool_call_id", None)
    if call_id:
        return (_ToolResultRow(str(call_id), observation, dispatch_error),)
    if observation is None and dispatch_error is None:
        return ()
    raise ToolResultAttributionError(
        "effect.execute: cannot attribute tool result to a declared call_id "
        f"(invocation_id={receipt.invocation_id}, outcome={receipt.outcome.value}); "
        "act.envelope must mint each envelope through ToolsEnvelopeMeta with tool_call_id"
    )


def _row_surface(row: _ToolResultRow, receipt: EffectReceipt) -> tuple[str, dict[str, Any] | None]:
    """Project one row onto the writer's ``(content, error)`` pair.

    A dispatch that raised has no Observation, so the receipt's classified
    error becomes the fact; ``derive_messages`` renders it as the
    model-visible text (an empty tool row is indistinguishable from an
    unanswered call).
    """
    if row.observation is not None:
        return observation_content(row.observation), observation_error(row.observation)
    message = row.dispatch_error or f"dispatch failed: {receipt.error_code or 'unknown'}"
    return "", {
        "kind": receipt.failure_kind or "execution",
        "message": message,
        "retryable": bool(receipt.retryable),
    }


def _append_tool_result_surface(
    context: NodeContext,
    envelope: CommandEnvelope,
    receipt: EffectReceipt,
    observation: Observation | None,
    dispatch_error: str | None,
    decision: Decision | None = None,
) -> None:
    """Append one ``surface/tool_result`` per executed call id.

    This is the only path by which a tool result becomes model-visible,
    so every declared call must be answered — including the calls of a
    multi-call turn and the call whose dispatch raised. Journal-write
    failures stay best-effort (the side effect already happened and must
    not be rolled back); attribution failures raise instead.
    """
    rows = _owed_rows(envelope, receipt, observation, dispatch_error, decision=decision)
    if not rows:
        return
    writer = resolve_writer(context=context, node="effect.execute", required=False)
    if writer is None:
        _log.debug(
            "effect.execute: no bound writer; tool result not surfaced (invocation_id=%s)",
            receipt.invocation_id,
        )
        return
    state = getattr(context.runtime, "state", None)
    step = getattr(state, "step", 0) or 0
    # Source-aware verification (ProvenanceGuard): mint a stable SourceRef for
    # every model-visible tool result so the source identity travels with the
    # evidence instead of collapsing into anonymous context. Additive only —
    # existing attribution (call_id) and content contracts are unchanged.
    from lca.infrastructure.source_verify.registry import (
        ensure_registry,
        source_marker,
    )

    registry = ensure_registry(getattr(context, "runtime", None))
    for row in rows:
        content, error = _row_surface(row, receipt)
        ref = registry.register_tool_result(
            call_id=row.call_id,
            tool_name=receipt.provider or "",
            content=content,
            label=receipt.provider or "",
        )
        marked = source_marker(ref.source_id)
        content = f"{marked}\n{content}" if content else marked
        try:
            writer.append_tool_result(
                turn=step,
                step=step,
                call_id=row.call_id,
                content=content,
                error=error,
                meta={
                    "tool_name": receipt.provider,
                    "outcome": receipt.outcome.value,
                    "invocation_id": receipt.invocation_id,
                    "source_id": ref.source_id,
                },
            )
        except Exception:
            _log.exception(
                "effect.execute: failed to append surface/tool_result (call_id=%s)",
                row.call_id,
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
    envelope: CommandEnvelope,
    context: NodeContext,
    decision: Decision | None,
    state: AgentState | None,
) -> tuple[EffectReceipt, Observation | None, str | None]:
    """Dispatch the CommandEnvelope through the EffectDispatcher capability.

    Returns the receipt, the executed Observation (``None`` when the
    result is not an Observation, e.g. ``memory.update``'s dict receipt),
    and the classified dispatch error text (``None`` when the gateway
    returned normally), so the node can project a model-visible
    ``surface/tool_result`` row without re-parsing the stringified
    ``output_ref`` — including for a dispatch that raised.

    ADR-0235 / PR-5: ``decision`` / ``state`` are typed kwargs forwarded
    to ``gateway.execute`` as typed keyword-only parameters; the dispatcher
    does not read them off ``envelope.metadata``.
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

    # ADR-0292 section 9 wiring 3: bind the executing decision as ambient
    # while tools run, so the standing-write tools read its instruction
    # source (``get_current_decision().content_origin``) instead of taking
    # an origin parameter. ``decision`` is None on legacy paths: no scope,
    # tools see unbound (permissive) exactly as before.
    scope = decision_scope(decision) if decision is not None else nullcontext()
    try:
        with scope:
            output = await gateway.execute(envelope, policy, decision=decision, state=state)
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
            f"{type(exc).__name__}: {exc}",
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
        None,
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


__all__ = ["EffectExecuteExecutor", "ToolResultAttributionError", "setup"]
