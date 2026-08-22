"""将已组装的既有认知组件适配到 ADR-0075 的声明式执行路径。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.result import Result
from lca.contracts.protocols.command_envelope import RunDelta
from lca.contracts.protocols.plan import CompiledRunPlan
from lca.harness.declarative import (
    GenericPlanInterpreter,
    GraphAssembler,
    MappingRestrictedScope,
)
from lca.layer2_runtime.completion.artifact_closure import synthesize_artifact_closure


@dataclass(frozen=True, slots=True)
class RuntimePhaseCapabilities:
    """内置阶段实现可见的受限 facade，不公开 live composition scope。"""

    brain: Any
    body: Any
    memory: Any
    perceive_hub: Any
    stop_rule: Any


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
            reducer=ReducerDeltaAdapter(self._reducer)
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


__all__ = ["DeclarativeRuntimeDriver", "ReducerDeltaAdapter", "RuntimePhaseCapabilities"]
