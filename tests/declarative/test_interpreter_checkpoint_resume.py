from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from lca.contracts.protocols.declarative_phase_graph import PhaseRunCursor


def test_phase_run_cursor_is_immutable_and_contains_only_resume_data() -> None:
    cursor = PhaseRunCursor(
        plan_ref="plan:test",
        node_id="reflect.main",
        visit_counts=(("act.main", 1),),
        edge_counts=(("act.main", "reflect.main", 1),),
        artifacts={"observation": {"success": True}},
        causation_refs=("receipt:act:1",),
        budget_snapshot={"steps_remaining": 3},
    )

    assert cursor.plan_ref == "plan:test"
    assert cursor.node_id == "reflect.main"
    assert cursor.visit_count_for("act.main") == 1
    assert cursor.edge_count_for("act.main", "reflect.main") == 1
    assert cursor.artifacts["observation"] == {"success": True}

    with pytest.raises(FrozenInstanceError):
        cursor.node_id = "stop.main"  # type: ignore[misc]


class _ReceiptGateway:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, _envelope, _policy):
        self.calls += 1
        return {"receipt": "confirmed"}


class _PhaseExecutor:
    def __init__(self, phase) -> None:
        self.phase = phase

    async def execute(self, context, _input):
        from types import SimpleNamespace

        from lca.contracts.protocols.command_envelope import CapabilityGrant, mint_envelope
        from lca.contracts.protocols.declarative_phase_graph import PhaseResult, SemanticPhase

        if self.phase is SemanticPhase.PERCEIVE:
            return PhaseResult(result_kind="context", payload={"task": "resume"})
        if self.phase is SemanticPhase.THINK:
            return PhaseResult(
                result_kind="decision", payload=SimpleNamespace(decision_id="decision:resume")
            )
        if self.phase is SemanticPhase.ACT:
            decision = context.artifacts["think"]
            return PhaseResult(
                result_kind="observation",
                command_envelope=mint_envelope(
                    plan_ref=context.plan_ref,
                    scope_ref=context.node_ref,
                    decision=decision,
                    provider="test.effect",
                    grant=CapabilityGrant(
                        capability="test.effect", scope="run", effect_class="tools"
                    ),
                    idempotency_key="effect:resume-once",
                    metadata={"effect_class": "tools"},
                ),
            )
        if self.phase is SemanticPhase.REFLECT:
            return PhaseResult(result_kind="reflection", payload={"ok": True})
        if self.phase is SemanticPhase.REMEMBER:
            return PhaseResult(result_kind="write_set", payload={"ok": True})
        return PhaseResult(result_kind="stop_decision", payload={"should_stop": True})


@pytest.mark.asyncio
async def test_resume_continues_at_saved_node_without_reexecuting_confirmed_effect() -> None:
    from lca.contracts.protocols.declarative_phase_graph import SemanticPhase
    from lca.harness.declarative import (
        GenericPlanInterpreter,
        GraphAssembler,
        MappingRestrictedScope,
    )
    from lca.harness.profile.plan_compiler import compile_plan
    from lca.harness.profile.resolve import resolve_profile

    plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
    executable = GraphAssembler().assemble(
        plan,
        MappingRestrictedScope(
            {f"phase.{phase.value}.standard": _PhaseExecutor(phase) for phase in SemanticPhase}
        ),
    )
    gateway = _ReceiptGateway()
    interpreter = GenericPlanInterpreter(effect_gateway=gateway)

    paused = await interpreter.run_until_safe_boundary(executable, state={}, max_nodes=3)

    assert paused.cursor is not None
    assert paused.cursor.node_id == "reflect.main"
    assert gateway.calls == 1

    resumed = await interpreter.resume(executable, state=paused.state, cursor=paused.cursor)

    assert resumed.terminal_node == "stop.main"
    assert gateway.calls == 1


class _PauseContribution:
    async def execute(self, _context, _input):
        from lca.contracts.protocols.declarative_phase_graph import PhaseResult

        return PhaseResult(
            result_kind="policy",
            payload={"verdict": "pause", "reason": "approval required"},
        )


@pytest.mark.asyncio
async def test_govern_pause_returns_journal_backed_resumable_outcome() -> None:
    from dataclasses import replace

    from lca.contracts.protocols.declarative_phase_graph import (
        ContributionRole,
        PhaseContribution,
        SemanticPhase,
    )
    from lca.harness.declarative import (
        GenericPlanInterpreter,
        GraphAssembler,
        MappingRestrictedScope,
    )
    from lca.harness.profile.plan_compiler import compile_plan
    from lca.harness.profile.resolve import resolve_profile

    standard_plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
    pause = PhaseContribution(
        phase=SemanticPhase.THINK,
        role=ContributionRole.GOVERN,
        executor="control.pause.fixture",
        output="control.pause",
        aggregation="first-terminal",
    )
    plan = replace(
        standard_plan,
        phase_bindings=tuple(
            replace(binding, contributions=(*binding.contributions, pause))
            if binding.semantic_phase is SemanticPhase.THINK
            else binding
            for binding in standard_plan.phase_bindings
        ),
    )
    executable = GraphAssembler().assemble(
        plan,
        MappingRestrictedScope(
            {
                **{
                    f"phase.{phase.value}.standard": _PhaseExecutor(phase)
                    for phase in SemanticPhase
                },
                "control.pause.fixture": _PauseContribution(),
            }
        ),
    )
    result = await GenericPlanInterpreter().run(executable, state={})

    assert result.outcome is not None
    assert result.outcome.kind == "paused"
    assert result.cursor is not None
    assert any(fact.kind == "run.paused" for fact in result.facts)


class _UncertainGateway:
    async def execute(self, _envelope, _policy):
        from lca.contracts.protocols.declarative_phase_graph import DeclarativeValidationError

        raise DeclarativeValidationError("RT-003", "effect receipt cannot be confirmed")


@pytest.mark.asyncio
async def test_unconfirmed_effect_receipt_returns_effect_uncertain_outcome() -> None:
    from lca.contracts.protocols.declarative_phase_graph import SemanticPhase
    from lca.harness.declarative import (
        GenericPlanInterpreter,
        GraphAssembler,
        MappingRestrictedScope,
    )
    from lca.harness.profile.plan_compiler import compile_plan
    from lca.harness.profile.resolve import resolve_profile

    plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
    executable = GraphAssembler().assemble(
        plan,
        MappingRestrictedScope(
            {f"phase.{phase.value}.standard": _PhaseExecutor(phase) for phase in SemanticPhase}
        ),
    )

    result = await GenericPlanInterpreter(effect_gateway=_UncertainGateway()).run(
        executable, state={}
    )

    assert result.outcome is not None
    assert result.outcome.kind == "effect_uncertain"
    assert result.cursor is not None
    assert any(fact.kind == "run.effect_uncertain" for fact in result.facts)
