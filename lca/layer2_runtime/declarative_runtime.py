"""将已组装的既有认知组件适配到 ADR-0075 的声明式执行路径。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.enums import SnapshotReason
from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.result import Result
from lca.contracts.protocols.command_envelope import CommandEnvelope, RunDelta, RunFact
from lca.contracts.protocols.declarative_phase_graph import (
    DeclarativeCheckpoint,
    DeclarativeValidationError,
    EffectGateway,
    EffectPolicyPlan,
    JournalCommitter,
    PhaseInput,
    PhaseRunCursor,
)
from lca.contracts.protocols.plan import CompiledRunPlan
from lca.harness.declarative import (
    GenericPlanInterpreter,
    GraphAssembler,
    MappingRestrictedScope,
)
from lca.layer0_infra.observability import record_runtime
from lca.layer2_runtime.completion.artifact_closure import synthesize_artifact_closure


@dataclass(frozen=True, slots=True)
class RuntimePhaseCapabilities:
    """内置阶段实现可见的受限 facade，不公开 live composition scope。"""

    brain: Any
    body: Any
    memory: Any
    perceive_hub: Any
    stop_rule: Any


class RuntimeJournalCommitter(JournalCommitter):
    """将通用解释器产生的事实写入当前已绑定的正式 Journal backend。"""

    def __init__(self) -> None:
        self._sequence = 0

    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> str:
        return self._record(
            operation="phase.fact",
            source=node_ref,
            plan_ref=plan_ref,
            attributes={"fact_id": fact.fact_id, "kind": fact.kind, "payload": dict(fact.payload)},
        )

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str:
        return self._record(
            operation="phase.evidence",
            source=node_ref,
            plan_ref=plan_ref,
            attributes={"evidence_ref": evidence_ref},
        )

    def commit_observation(self, observation: Any, *, plan_ref: str, node_ref: str) -> str:
        return self._record(
            operation="effect.receipt",
            source=node_ref,
            plan_ref=plan_ref,
            attributes={"observation_type": type(observation).__name__, "observation": observation},
        )

    def _record(
        self,
        *,
        operation: str,
        source: str,
        plan_ref: str,
        attributes: Mapping[str, Any],
    ) -> str:
        self._sequence += 1
        stamped = record_runtime(
            "journal",
            operation,
            plugin=source,
            attributes={"plan_ref": plan_ref, **dict(attributes)},
        )
        event_id = getattr(stamped, "event_id", "") if stamped is not None else ""
        return event_id or f"{plan_ref}:{source}:{operation}:{self._sequence}"


class RuntimeEffectGateway(EffectGateway):
    """按已绑定 capability 调用 effect handler 的通用网关。"""

    def __init__(
        self,
        _capabilities: RuntimePhaseCapabilities,
        *,
        effect_handlers: Mapping[str, Any] | None = None,
    ) -> None:
        self._capabilities = _capabilities
        self._effect_handlers = dict(effect_handlers or {})

    async def execute(self, envelope: CommandEnvelope, policy: EffectPolicyPlan) -> Any:
        metadata = envelope.metadata
        effect_class = str(metadata.get("effect_class", envelope.grant.effect_class))
        if effect_class not in policy.allowed_effects:
            raise DeclarativeValidationError(
                "PS-006", f"effect class is denied by plan: {effect_class}"
            )
        if effect_class in policy.idempotency_required and not envelope.idempotency_key:
            raise DeclarativeValidationError("PS-006", "effect requires an idempotency key")
        if effect_class in policy.approval_required and not bool(metadata.get("approved", False)):
            raise DeclarativeValidationError("PS-006", f"effect requires approval: {effect_class}")
        capability = envelope.grant.capability
        handler = self._effect_handlers.get(capability)
        if handler is None:
            raise DeclarativeValidationError(
                "PG-003", f"no effect handler bound for capability: {capability}"
            )
        execute = getattr(handler, "execute", None)
        if not callable(execute):
            raise DeclarativeValidationError(
                "PS-002", f"effect handler is not executable: {capability}"
            )
        return await execute(envelope, self._capabilities)


class ReducerDeltaAdapter:
    """把 PhaseResult 的 RunDelta 交给既有 Reducer 的唯一状态写入接口。"""

    def __init__(self, reducer: Any) -> None:
        self._reducer = reducer

    def apply_delta(self, state: Any, delta: RunDelta) -> Any:
        metadata = delta.metadata
        operation = metadata.get("operation") if isinstance(metadata, Mapping) else None
        if operation == "step":
            return self._reducer.apply_step_advanced(state, int(metadata.get("step", state.step)))
        if operation == "perception":
            return self._reducer.apply_perception(state, metadata["manifest"])
        if operation == "turn":
            return self._reducer.apply_turn(
                state,
                Turn(
                    decision=metadata["decision"],
                    observation=metadata["observation"],
                    reflection=metadata["reflection"],
                ),
            )
        if operation == "memory":
            return self._reducer.apply_memory(state, None)
        if operation == "stop":
            return self._reducer.apply_stop(state, metadata["stop"])
        return state


class DeclarativeRuntimeDriver:
    """运行已验证 PhaseGraph；业务阶段能力均由 plan binding 选择。"""

    def __init__(
        self,
        *,
        plan: CompiledRunPlan,
        phase_executors: Mapping[str, Any],
        capabilities: RuntimePhaseCapabilities,
        reducer: Any,
        hooks: Any,
        state_store: Any | None = None,
        effect_handlers: Mapping[str, Any] | None = None,
    ) -> None:
        self._plan = plan
        self._phase_executors = phase_executors
        self._capabilities = capabilities
        self._reducer = reducer
        self._hooks = hooks
        self._state_store = state_store
        self._effect_handlers = dict(effect_handlers or {})

    async def execute(self, state: Any) -> Result:
        interpretation = await self._interpret(state)
        return await self._result_from_interpretation(interpretation)

    async def resume_from_checkpoint(
        self,
        checkpoint: DeclarativeCheckpoint,
        *,
        input: object | None = None,
    ) -> Result:
        if checkpoint.plan_ref != self._plan_ref:
            raise DeclarativeValidationError(
                "RT-004", "checkpoint plan_ref differs from bound declarative plan"
            )
        if self._state_store is None:
            raise DeclarativeValidationError("RT-004", "declarative resume requires a StateStore")
        state = await self._state_store.load(checkpoint.state_snapshot.state_ref)
        state = self._reducer.apply_resume(state, input, None)
        interpretation = await self._interpret(
            state,
            cursor=checkpoint.cursor,
            input=PhaseInput(artifact=input) if input is not None else None,
        )
        return await self._result_from_interpretation(interpretation)

    @property
    def _plan_ref(self) -> str:
        from lca.contracts.protocols.plan import compiled_run_plan_ref

        return compiled_run_plan_ref(self._plan)

    async def _interpret(
        self,
        state: Any,
        *,
        cursor: PhaseRunCursor | None = None,
        input: PhaseInput | None = None,
    ) -> Any:
        executable = GraphAssembler().assemble(
            self._plan,
            MappingRestrictedScope(self._phase_executors),
        )
        return await GenericPlanInterpreter(
            journal=RuntimeJournalCommitter(),
            effect_gateway=RuntimeEffectGateway(
                self._capabilities,
                effect_handlers=self._effect_handlers,
            ),
            reducer=ReducerDeltaAdapter(self._reducer),
        ).run(
            executable,
            state=state,
            input=input,
            budget=state.budget,
            capabilities=self._capabilities,
            artifacts={"task": state.task},
            cursor=cursor,
        )

    async def _result_from_interpretation(self, interpretation: Any) -> Result:
        state = interpretation.state
        outcome = interpretation.outcome
        if outcome is not None and outcome.kind in {"paused", "effect_uncertain"}:
            checkpoint = await self._save_checkpoint(
                state,
                outcome.cursor,
                SnapshotReason.PRE_APPROVAL
                if outcome.kind == "paused"
                else SnapshotReason.ON_ERROR,
            )
            state = self._reducer.apply_paused(state, checkpoint.state_snapshot.state_ref)
            await self._hooks.trigger("on_pause", state)
            result = Result.from_state(state)
            result.extra.update(
                {
                    "declarative_checkpoint": checkpoint,
                    "outcome": outcome.kind,
                    "phase_cursor": outcome.cursor,
                    "plan_ref": checkpoint.plan_ref,
                }
            )
            if outcome.kind == "paused" and outcome.error_fact is not None:
                approval_request = outcome.error_fact.payload.get("approval_request")
                if approval_request is not None:
                    result.extra["approval_request"] = approval_request
            return result
        if outcome is not None and outcome.kind == "failed":
            state = self._reducer.apply_error(state, RuntimeError("declarative run failed"))
            result = Result.from_state(state)
            result.extra.update({"outcome": "failed", "plan_ref": self._plan_ref})
            return result
        await self._hooks.trigger("on_complete", state)
        state = self._reducer.apply_artifact_closure(state, synthesize_artifact_closure() or "")
        result = Result.from_state(state)
        result.extra.update({"outcome": "completed", "plan_ref": self._plan_ref})
        return result

    async def _save_checkpoint(
        self,
        state: Any,
        cursor: PhaseRunCursor | None,
        reason: SnapshotReason,
    ) -> DeclarativeCheckpoint:
        if cursor is None:
            raise DeclarativeValidationError("RT-004", "resumable outcome has no cursor")
        if self._state_store is None:
            raise DeclarativeValidationError("RT-004", "declarative pause requires a StateStore")
        snapshot = state.snapshot(reason=reason)
        try:
            reference = await self._state_store.save(state)
        except Exception:
            checkpoints = getattr(state, "checkpoints", None)
            if isinstance(checkpoints, list) and checkpoints and checkpoints[-1] is snapshot:
                checkpoints.pop()
            raise
        snapshot.state_ref = reference
        return DeclarativeCheckpoint(
            state_snapshot=snapshot,
            cursor=cursor,
            plan_ref=self._plan_ref,
        )


__all__ = [
    "DeclarativeCheckpoint",
    "DeclarativeRuntimeDriver",
    "ReducerDeltaAdapter",
    "RuntimeEffectGateway",
    "RuntimeJournalCommitter",
    "RuntimePhaseCapabilities",
]
