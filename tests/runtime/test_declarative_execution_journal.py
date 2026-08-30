"""Tests for explicit runtime journal ownership in declarative execution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lca.contracts.models.core.state import AgentState, Budget
from lca.harness.declarative.lifecycle.phase_observation import NullPhaseObserver
from lca.runtime.declarative_runtime import (
    DeclarativeExecution,
    DeclarativeRuntimeDriver,
    RuntimePhaseCapabilities,
)
from lca.runtime.runtime_bindings import DeclarativeRuntimeBindings
from lca.runtime.runtime_journal import RuntimeJournalCommitter


class _Journal:
    """Minimal journal double that makes Turn sequence ownership observable."""

    def __init__(self, sequence: int) -> None:
        self.sequence = sequence

    def commit_fact(self, *args: object, **kwargs: object) -> str:
        return "fact"

    def commit_evidence(self, *args: object, **kwargs: object) -> str:
        return "evidence"

    def commit_observation(self, *args: object, **kwargs: object) -> str:
        return "observation"


def _state() -> AgentState:
    return AgentState(trace_id="trace-journal", task="journal ownership", budget=Budget())


@pytest.mark.asyncio
async def test_declarative_execution_uses_the_injected_turn_journal() -> None:
    """The execution module must not create or replace the caller's journal adapter."""

    journal = _Journal(sequence=7)
    finalizer = MagicMock()
    finalizer.finalize = AsyncMock(return_value="carrier-result")
    bindings = DeclarativeRuntimeBindings.assemble(
        plan=MagicMock(),
        phase_executors={},
        capabilities=RuntimePhaseCapabilities(
            {
                "brain": MagicMock(),
                "body": MagicMock(),
                "memory": MagicMock(),
                "perceive_hub": MagicMock(),
                "stop_policy": MagicMock(),
            }
        ),
        reducer=MagicMock(),
        hooks=MagicMock(),
        effect_handler_registry=MagicMock(),
        delta_handler_registry=MagicMock(),
        artifact_closure=MagicMock(),
        idempotency_store=MagicMock(),
        resume_input_adapter=MagicMock(),
        state_store=MagicMock(),
        effect_gateway_factory=MagicMock(),
        delta_reducer_factory=MagicMock(),
        journal_factory=MagicMock(),
        interpreter_factory=MagicMock(),
        checkpoint_state_resolver_factory=MagicMock(),
        result_finalizer_factory=MagicMock(),
        phase_observer=NullPhaseObserver(),
    )
    fresh_state = bindings.new_state(
        trace_id="fresh-trace",
        task="fresh task",
        budget=Budget(max_steps=3),
        agent_role="runtime-role",
        from_role="caller-role",
        team_awareness=None,
    )
    assert fresh_state.trace_id == "fresh-trace"
    assert fresh_state.task == "fresh task"
    assert fresh_state.budget.max_steps == 3
    assert fresh_state.agent_role == "runtime-role"
    assert fresh_state.from_role == "caller-role"

    custom_interpreter = SimpleNamespace(run=AsyncMock(), resume=AsyncMock())
    bindings.interpreter_factory.create.return_value = custom_interpreter
    assert bindings.new_interpreter(journal=journal) is custom_interpreter
    bindings.interpreter_factory.create.assert_called_once_with(
        journal=journal,
        effect_gateway=bindings.effect_gateway_factory.create.return_value,
        reducer=bindings.delta_reducer_factory.create.return_value,
        phase_observer=bindings.phase_observer,
        lifecycle_publisher=bindings.lifecycle_publisher,
    )

    execution = DeclarativeExecution(
        bindings,
        journal=journal,
        result_finalizer=finalizer,
    )
    interpretation = object()

    with (
        patch("lca.runtime.declarative_runtime.GraphAssembler") as assembler,
        patch(
            "lca.runtime.runtime_bindings.DeclarativeRuntimeBindings.new_interpreter"
        ) as interpreter_factory,
        patch(
            "lca.runtime.runtime_bindings.DeclarativeRuntimeBindings.require_executable_plan",
            return_value=bindings.plan,
        ),
        patch(
            "lca.runtime.runtime_bindings.DeclarativeRuntimeBindings.plan_ref",
            return_value="compiled-plan-ref",
        ),
    ):
        assembler.return_value.assemble.return_value = object()
        interpreter = interpreter_factory.return_value
        interpreter.run = AsyncMock(return_value=interpretation)

        result = await execution.execute(_state())

    assert result == "carrier-result"
    interpreter_factory.assert_called_once_with(journal=journal)
    assert interpreter.run.await_args.args[0] is assembler.return_value.assemble.return_value
    finalizer.finalize.assert_awaited_once_with(
        interpretation=interpretation,
        plan_ref="compiled-plan-ref",
        journal_sequence=7,
    )


def test_runtime_bindings_reject_missing_phase_executor() -> None:
    """A non-empty executor map is insufficient when a plan binding is absent."""
    bindings = DeclarativeRuntimeBindings.assemble(
        plan=SimpleNamespace(
            phase_bindings=(SimpleNamespace(executor_capability="phase.missing"),),
        ),
        phase_executors={"phase.present": object()},
        capabilities=MagicMock(),
        reducer=MagicMock(),
        hooks=MagicMock(),
        effect_handler_registry=MagicMock(),
        delta_handler_registry=MagicMock(),
        artifact_closure=MagicMock(),
        idempotency_store=MagicMock(),
        resume_input_adapter=MagicMock(),
        state_store=MagicMock(),
        effect_gateway_factory=MagicMock(),
        delta_reducer_factory=MagicMock(),
        journal_factory=MagicMock(),
        interpreter_factory=MagicMock(),
        checkpoint_state_resolver_factory=MagicMock(),
        result_finalizer_factory=MagicMock(),
        phase_observer=NullPhaseObserver(),
    )

    with pytest.raises(ValueError, match=r"phase\.missing"):
        bindings.require_executable_plan()


@pytest.mark.asyncio
async def test_runtime_driver_uses_execution_owned_plan_reference_on_resume() -> None:
    """恢复校验必须复用执行闭包已验证的计划引用。"""

    bindings = MagicMock()
    driver = DeclarativeRuntimeDriver(bindings, journal=MagicMock())
    checkpoint = MagicMock(cursor=MagicMock())
    loaded_state = _state()
    driver._execution = MagicMock(plan_ref="execution-plan-ref")
    driver._execution.execute = AsyncMock(return_value="carrier-result")
    driver._checkpoint_state_resolver.resolve = AsyncMock(return_value=loaded_state)

    result = await driver.resume(checkpoint)

    assert result == "carrier-result"
    driver._checkpoint_state_resolver.resolve.assert_awaited_once_with(
        checkpoint,
        expected_plan_ref="execution-plan-ref",
    )
    driver._execution.execute.assert_awaited_once_with(loaded_state, cursor=checkpoint.cursor)


def test_runtime_journal_committer_exposes_monotonic_turn_sequence() -> None:
    """The runtime adapter reports the same sequence that finalization consumes."""

    journal = RuntimeJournalCommitter()

    with patch("lca.runtime.runtime_journal.record_runtime", return_value=None):
        first = journal.commit_evidence("evidence-1", plan_ref="plan", node_ref="think")
        second = journal.commit_observation({"ok": True}, plan_ref="plan", node_ref="act")

    assert first == "plan:think:phase.evidence:1"
    assert second == "plan:act:effect.receipt:2"
    assert journal.sequence == 2
