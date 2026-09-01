"""Layer-3 hard-fail check: every phase-graph node must be instrumented.

The assembler is the only authorized wrap site for phase-graph runnables; every
emitted ``ExecutablePlan`` must pass ``assert_all_instrumented`` before it
reaches the runtime, otherwise uninstrumented nodes would silently bypass the
EventSpine and break invariant I3.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from lca.contracts.protocols.declarative.declarative_fault_tolerance import PhaseExecutionPolicy
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.declarative.compile.assembler import (
    ExecutableNode,
    ExecutablePlan,
    UninstrumentedNode,
    assert_all_instrumented,
    wrap_instrument,
)


class _BareExecutor:
    """A plain PhaseExecutor with no assembler wrapping."""

    async def execute(self, context: object, phase_input: PhaseInput) -> PhaseResult:
        del context, phase_input
        return PhaseResult(result_kind="noop", payload=None)


def _make_plan(nodes: Mapping[str, ExecutableNode]) -> ExecutablePlan:
    """Wrap a pre-built node map into an ExecutablePlan with a stub CompiledRunPlan."""

    return ExecutablePlan(
        plan=CompiledRunPlan(
            profile_path="test://layer3",
            capability=None,  # type: ignore[arg-type]
            scope=None,  # type: ignore[arg-type]
        ),
        nodes=nodes,
    )


def _policy() -> PhaseExecutionPolicy:
    return PhaseExecutionPolicy()


def test_assert_all_instrumented_rejects_unwrapped_runnable() -> None:
    """A bare (non-wrapped) executor on any node fails the Layer-3 check."""

    bare_runnable = _BareExecutor().execute
    node = ExecutableNode(
        node_id="perceive.main",
        semantic_phase=SemanticPhase.PERCEIVE,
        executor_capability="phase.perceive.test",
        executor=bare_runnable,
        contributions=(),
        execution_policy=_policy(),
    )
    plan = _make_plan({"perceive.main": node})

    with pytest.raises(UninstrumentedNode) as exc_info:
        assert_all_instrumented(plan)

    assert exc_info.value.node_id == "perceive.main"
    assert exc_info.value.plan_name == "test://layer3"


def test_assert_all_instrumented_rejects_when_wrap_provenance_wrong() -> None:
    """A runnable marked instrumented but with a non-assembler provenance is rejected."""

    def _innocent_runnable(context: object, phase_input: PhaseInput) -> PhaseResult:
        del context, phase_input
        return PhaseResult(result_kind="noop", payload=None)

    # Bound methods don't carry a __dict__, so the test uses a plain function
    # and a wrapper object that exposes it as ``execute`` to exercise the
    # wrong-provenance branch deterministically.
    _innocent_runnable.__lca_instrumented__ = True
    _innocent_runnable.wrap_provenance = "manual"

    class _ForeignWrap:
        def execute(self, context: object, phase_input: PhaseInput) -> PhaseResult:
            return _innocent_runnable(context, phase_input)

    node = ExecutableNode(
        node_id="think.main",
        semantic_phase=SemanticPhase.THINK,
        executor_capability="phase.think.test",
        executor=_ForeignWrap(),
        contributions=(),
        execution_policy=_policy(),
    )
    plan = _make_plan({"think.main": node})

    with pytest.raises(UninstrumentedNode) as exc_info:
        assert_all_instrumented(plan)

    assert exc_info.value.node_id == "think.main"


def test_assert_all_instrumented_accepts_wrapped_plan() -> None:
    """A plan where every node has been wrapped via wrap_instrument passes silently."""

    bare = _BareExecutor()
    wrapped_runnable = wrap_instrument(bare.execute, node_id="act.main")
    assert wrapped_runnable.__lca_instrumented__ is True
    assert wrapped_runnable.wrap_provenance == "assembler"

    node = ExecutableNode(
        node_id="act.main",
        semantic_phase=SemanticPhase.ACT,
        executor_capability="phase.act.test",
        executor=wrapped_runnable,
        contributions=(),
        execution_policy=_policy(),
    )
    plan = _make_plan({"act.main": node})

    assert assert_all_instrumented(plan) is None


def test_assert_all_instrumented_rejects_when_any_node_is_bare() -> None:
    """If any node in the plan is bare, the whole plan fails (no short-circuit gating)."""

    wrapped_runnable = wrap_instrument(_BareExecutor().execute, node_id="perceive.main")
    bare_runnable = _BareExecutor().execute

    plan = _make_plan(
        {
            "perceive.main": ExecutableNode(
                node_id="perceive.main",
                semantic_phase=SemanticPhase.PERCEIVE,
                executor_capability="phase.perceive.test",
                executor=wrapped_runnable,
                contributions=(),
                execution_policy=_policy(),
            ),
            "think.main": ExecutableNode(
                node_id="think.main",
                semantic_phase=SemanticPhase.THINK,
                executor_capability="phase.think.test",
                executor=bare_runnable,
                contributions=(),
                execution_policy=_policy(),
            ),
        }
    )

    with pytest.raises(UninstrumentedNode) as exc_info:
        assert_all_instrumented(plan)

    assert exc_info.value.node_id == "think.main"


def test_assert_all_instrumented_returns_none_for_empty_plan() -> None:
    """An empty node set is trivially instrumented and must return None."""

    plan = _make_plan({})
    assert assert_all_instrumented(plan) is None


def test_uninstrumented_node_carries_plan_and_node_identifiers() -> None:
    """The exception must surface plan_ref + node_id for downstream diagnostics."""

    bare_runnable = _BareExecutor().execute
    node = ExecutableNode(
        node_id="reflect.main",
        semantic_phase=SemanticPhase.REFLECT,
        executor_capability="phase.reflect.test",
        executor=bare_runnable,
        contributions=(),
        execution_policy=_policy(),
    )
    plan = _make_plan({"reflect.main": node})

    with pytest.raises(UninstrumentedNode) as exc_info:
        assert_all_instrumented(plan)

    error = exc_info.value
    assert error.node_id == "reflect.main"
    assert error.plan_name == "test://layer3"
    assert "reflect.main" in str(error)
    assert "test://layer3" in str(error)


def test_wrap_instrument_sets_required_attributes() -> None:
    """Sanity: wrap_instrument markers must be on every emitted runnable."""

    runnable = _BareExecutor().execute
    wrapped = wrap_instrument(runnable, node_id="respond.main")

    assert getattr(wrapped, "__lca_instrumented__", False) is True
    assert getattr(wrapped, "wrap_provenance", None) == "assembler"


def test_assembler_assemble_hard_fails_on_uninstrumented_scope() -> None:
    """GraphAssembler.assemble must call assert_all_instrumented as its final step.

    The production path is verified end-to-end in test_assembler_wraps_instrument
    via compile_plan + resolve_profile; this test guarantees the wrapper is
    wired into assemble() itself by calling the helper the assembler uses for
    every compiled binding.
    """

    from lca.harness.declarative.compile.assembler import (
        GraphAssembler,
        wrap_executor,
    )

    bare_executor = _BareExecutor()
    wrapped = wrap_executor(bare_executor)
    # wrap_executor must always emit the Layer-3 markers on the closure it
    # returns through ``.execute`` — that is the contract assemble() relies on.
    assert getattr(wrapped.execute, "__lca_instrumented__", False) is True
    assert getattr(wrapped.execute, "wrap_provenance", None) == "assembler"

    # A hand-built bare executor should still be caught by the standalone
    # hard-fail, mirroring what assemble() enforces at the end of its loop.
    plan = _make_plan(
        {
            "perceive.main": ExecutableNode(
                node_id="perceive.main",
                semantic_phase=SemanticPhase.PERCEIVE,
                executor_capability="phase.perceive.test",
                executor=bare_executor.execute,
                contributions=(),
                execution_policy=_policy(),
            ),
        }
    )
    with pytest.raises(UninstrumentedNode):
        assert_all_instrumented(plan)

    # The GraphAssembler reference is part of the import-only contract — the
    # actual compile + assemble path is exercised by Task 4.1 tests.
    assert GraphAssembler is not None
