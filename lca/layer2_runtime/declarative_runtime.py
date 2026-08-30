"""Adapt one verified declarative runtime binding into fresh and resume execution."""

from __future__ import annotations

from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.declarative_phase_graph import PhaseRunCursor
from lca.contracts.protocols.runtime_composition import ResultFinalizer
from lca.harness.declarative import GraphAssembler
from lca.layer2_runtime.checkpoint_resolution import DeclarativeCheckpoint
from lca.layer2_runtime.runtime_bindings import (
    DeclarativeRuntimeBindings,
    RuntimePhaseCapabilities,
)
from lca.layer2_runtime.runtime_journal import RuntimeJournal, RuntimeJournalCommitter


class DeclarativeExecution:
    """以一个已验证 binding 执行 fresh 或 resume 声明式 Turn。"""

    def __init__(
        self,
        bindings: DeclarativeRuntimeBindings,
        *,
        journal: RuntimeJournal,
        result_finalizer: ResultFinalizer,
    ) -> None:
        self._bindings = bindings
        self._journal = journal
        self._result_finalizer = result_finalizer

    async def execute(
        self,
        state: AgentState,
        *,
        cursor: PhaseRunCursor | None = None,
    ) -> Result:
        """以同一执行闭包解释新状态或恢复 cursor。"""

        plan = self._bindings.require_executable_plan()
        executable = GraphAssembler().assemble(
            plan,
            self._bindings.phase_scope(),
        )
        interpreter = self._bindings.new_interpreter(journal=self._journal)
        if cursor is None:
            interpretation = await interpreter.run(
                executable,
                state=state,
                budget=state.budget,
                capabilities=self._bindings.capabilities,
                artifacts={"task": state.task},
            )
        else:
            interpretation = await interpreter.resume(
                executable,
                state=state,
                cursor=cursor,
                budget=state.budget,
                capabilities=self._bindings.capabilities,
            )
        return await self._result_finalizer.finalize(
            interpretation=interpretation,
            plan_ref=self._bindings.plan_ref(),
            journal_sequence=self._journal.sequence,
        )

    @property
    def plan_ref(self) -> str:
        """返回执行闭包已验证计划的稳定引用。"""

        return self._bindings.plan_ref()


class DeclarativeRuntimeDriver:
    """由不可变运行 binding 构造的 carrier adapter。"""

    def __init__(self, bindings: DeclarativeRuntimeBindings, *, journal: RuntimeJournal) -> None:
        self._bindings = bindings
        self._checkpoint_state_resolver = bindings.new_checkpoint_state_resolver()
        result_finalizer = bindings.new_result_finalizer()
        self._execution = DeclarativeExecution(
            bindings,
            journal=journal,
            result_finalizer=result_finalizer,
        )

    async def run(self, state: AgentState) -> Result:
        """通过单一声明式 Turn module 执行新状态。"""

        return await self._execution.execute(state)

    async def resume(self, checkpoint: DeclarativeCheckpoint) -> Result:
        """先物化 checkpoint 状态，再委托共享 Turn module。"""

        loaded_state = await self._checkpoint_state_resolver.resolve(
            checkpoint,
            expected_plan_ref=self._execution.plan_ref,
        )
        return await self._execution.execute(loaded_state, cursor=checkpoint.cursor)


__all__ = [
    "DeclarativeCheckpoint",
    "DeclarativeExecution",
    "DeclarativeRuntimeDriver",
    "RuntimeJournalCommitter",
    "RuntimePhaseCapabilities",
]
