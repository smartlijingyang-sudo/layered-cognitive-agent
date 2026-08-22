"""将已组装的既有认知组件适配到 ADR-0075 的声明式执行路径。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.result import Result
from lca.contracts.protocols.command_envelope import CommandEnvelope, RunDelta, RunFact
from lca.contracts.protocols.declarative_phase_graph import (
    DeclarativeValidationError,
    EffectGateway,
    EffectPolicyPlan,
    JournalCommitter,
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
class ClaimResult:
    """幂等性 claim 的结果"""

    status: Literal["new", "completed", "in_progress"]
    receipt: Any | None = None


class RuntimeIdempotencyStore:
    """持久化幂等性 receipt store。

    确保同一 idempotency_key 在同一个 plan_ref 下至多执行一次。
    - new: 首次 claim，写入记录并继续执行
    - completed: 已完成，返回已有 receipt
    - in_progress: 正在执行中，表示 crash 后重试，应标记 effect_uncertain
    """

    def __init__(self) -> None:
        self._claims: dict[tuple[str, str], dict[str, Any]] = {}

    async def claim(self, plan_ref: str, idempotency_key: str) -> ClaimResult:
        """Claim 一个幂等性 key。

        Args:
            plan_ref: 计划引用
            idempotency_key: 幂等性 key

        Returns:
            ClaimResult: 包含状态和 receipt
        """
        key = (plan_ref, idempotency_key)

        if key in self._claims:
            record = self._claims[key]
            if record["status"] == "completed":
                return ClaimResult(status="completed", receipt=record["receipt"])
            else:
                # in_progress means crash during execution
                return ClaimResult(status="in_progress", receipt=None)

        # New claim - mark as in_progress
        self._claims[key] = {"status": "in_progress", "receipt": None}
        return ClaimResult(status="new", receipt=None)

    async def complete(self, plan_ref: str, idempotency_key: str, receipt: Any) -> None:
        """Mark a claim as completed with a receipt."""
        key = (plan_ref, idempotency_key)
        if key in self._claims:
            self._claims[key] = {"status": "completed", "receipt": receipt}


@dataclass(frozen=True, slots=True)
class DeclarativeCheckpoint:
    """声明式恢复所需的 checkpoint 数据"""

    state_snapshot: Any
    cursor: PhaseRunCursor
    plan_ref: str


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
    """声明式运行时唯一允许调用 body/memory 的受控 effect handler。"""

    def __init__(
        self,
        capabilities: RuntimePhaseCapabilities,
        idempotency_store: RuntimeIdempotencyStore | None = None,
    ) -> None:
        self._capabilities = capabilities
        self._idempotency_store = idempotency_store or RuntimeIdempotencyStore()

    async def execute(self, envelope: CommandEnvelope, policy: EffectPolicyPlan) -> Any:
        metadata = envelope.metadata
        effect_class = str(metadata.get("effect_class", envelope.grant.effect_class))
        if effect_class not in policy.allowed_effects:
            raise DeclarativeValidationError("PS-006", f"effect class is denied by plan: {effect_class}")
        if effect_class in policy.idempotency_required and not envelope.idempotency_key:
            raise DeclarativeValidationError("PS-006", "effect requires an idempotency key")

        # Check idempotency if key is present
        if envelope.idempotency_key:
            claim_result = await self._idempotency_store.claim(
                envelope.plan_ref, envelope.idempotency_key
            )
            if claim_result.status == "completed":
                # Already executed, return cached receipt
                return claim_result.receipt
            elif claim_result.status == "in_progress":
                # Crash during previous execution - effect uncertain
                raise DeclarativeValidationError(
                    "RT-003",
                    f"effect with idempotency_key {envelope.idempotency_key} was in_progress "
                    "when previous execution crashed; effect outcome uncertain",
                )
            # status == "new", continue with execution

        if effect_class in policy.approval_required and not bool(metadata.get("approved", False)):
            raise DeclarativeValidationError("PS-006", f"effect requires approval: {effect_class}")
        operation = metadata.get("operation")
        if operation == "body.act":
            state = metadata.get("state")
            decision = metadata.get("decision")
            if state is None or decision is None:
                raise DeclarativeValidationError("RT-002", "body effect lacks state or recorded Decision")
            result = await self._capabilities.body.act(decision, state)
            # Record receipt for idempotency
            if envelope.idempotency_key:
                receipt = {
                    "receipt": "body.acted",
                    "idempotency_key": envelope.idempotency_key,
                    "plan_ref": envelope.plan_ref,
                    "result": result,
                }
                await self._idempotency_store.complete(
                    envelope.plan_ref, envelope.idempotency_key, receipt
                )
                return receipt
            return result
        if operation == "memory.update":
            state = metadata.get("state")
            observation = metadata.get("observation")
            reflection = metadata.get("reflection")
            if state is None or observation is None or reflection is None:
                raise DeclarativeValidationError("RT-002", "memory effect lacks admitted WriteSet inputs")
            await self._capabilities.memory.update(state, observation, reflection)
            receipt = {
                "receipt": "memory.updated",
                "idempotency_key": envelope.idempotency_key,
                "plan_ref": envelope.plan_ref,
            }
            if envelope.idempotency_key:
                await self._idempotency_store.complete(
                    envelope.plan_ref, envelope.idempotency_key, receipt
                )
            return receipt
        raise DeclarativeValidationError("PG-003", f"undeclared effect operation: {operation}")


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
    ) -> None:
        self._plan = plan
        self._phase_executors = phase_executors
        self._capabilities = capabilities
        self._reducer = reducer
        self._hooks = hooks

    async def run(self, state: Any) -> Result:
        executable = GraphAssembler().assemble(
            self._plan,
            MappingRestrictedScope(self._phase_executors),
        )
        interpretation = await GenericPlanInterpreter(
            journal=RuntimeJournalCommitter(),
            effect_gateway=RuntimeEffectGateway(self._capabilities),
            reducer=ReducerDeltaAdapter(self._reducer),
        ).run(
            executable,
            state=state,
            budget=state.budget,
            capabilities=self._capabilities,
            artifacts={"task": state.task},
        )
        final_state = interpretation.state
        await self._hooks.trigger("on_complete", final_state)
        final_state = self._reducer.apply_artifact_closure(
            final_state, synthesize_artifact_closure() or ""
        )
        return Result.from_state(final_state)

    async def resume(self, checkpoint: DeclarativeCheckpoint) -> Result:
        """从 checkpoint 恢复执行

        Args:
            checkpoint: 包含 cursor 和 plan_ref 的恢复点

        Returns:
            Result: 执行结果

        Raises:
            DeclarativeValidationError: 如果 plan_ref 不匹配
        """
        # 验证 plan_ref 匹配
        if checkpoint.plan_ref != self._plan.plan_hash:
            raise DeclarativeValidationError(
                "PG-008",
                f"plan_ref mismatch: checkpoint.plan_ref ({checkpoint.plan_ref}) != plan.plan_hash ({self._plan.plan_hash})"
            )

        # 组装可执行计划
        executable = GraphAssembler().assemble(
            self._plan,
            MappingRestrictedScope(self._phase_executors),
        )

        # 使用 interpreter 的 resume 方法
        interpreter = GenericPlanInterpreter(
            journal=RuntimeJournalCommitter(),
            effect_gateway=RuntimeEffectGateway(self._capabilities),
            reducer=ReducerDeltaAdapter(self._reducer),
        )

        interpretation = await interpreter.resume(
            executable,
            state=checkpoint.state_snapshot.state,
            cursor=checkpoint.cursor,
        )

        # 映射 interpretation 到 Result
        final_state = interpretation.state
        await self._hooks.trigger("on_complete", final_state)
        final_state = self._reducer.apply_artifact_closure(
            final_state, synthesize_artifact_closure() or ""
        )
        return Result.from_state(final_state)


__all__ = [
    "ClaimResult",
    "DeclarativeCheckpoint",
    "DeclarativeRuntimeDriver",
    "ReducerDeltaAdapter",
    "RuntimeEffectGateway",
    "RuntimeIdempotencyStore",
    "RuntimeJournalCommitter",
    "RuntimePhaseCapabilities",
]
