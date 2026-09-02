"""Layer-3 contract: the phase graph assembler must wrap every node runnable.

The PR-4 spine mandate requires every ``ExecutableNode`` to ship with
``__lca_instrumented__`` set on its wrapped runnable so that build-time
checks can detect any node that escaped ``wrap_instrument`` (Layer-3
contract). The provenance marker ``wrap_provenance == "assembler"`` is
the stable signal the spine catalog uses to attribute the wrapper.

This test drives ``GraphAssembler.assemble`` with a hand-built plan so
the assertion isolates the wrap contract from the rest of the spine
profile-loading pipeline. A companion ``wrap_instrument`` direct test
keeps the marker semantics pinned independently of the assembler.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from lca.contracts.protocols.declarative.declarative_fault_tolerance import (
    PhaseExecutionPolicy,
)
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    PhaseInput,
    PhaseResult,
    SemanticPhase,
)
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.declarative.compile.assembler import (
    ExecutableNode,
    GraphAssembler,
    MappingRestrictedScope,
)
from lca.harness.declarative.compile.instrument_wrap import (
    ASSEMBLER_PROVENANCE,
    WRAP_INSTRUMENTED_ATTR,
    wrap_instrument,
)


class _RecordingExecutor:
    """Minimal :class:`PhaseExecutor` double used by the assembler tests."""

    async def execute(self, context: object, input: PhaseInput) -> PhaseResult:
        del context, input
        return PhaseResult(result_kind="noop")


def _compile_single_node_plan() -> CompiledRunPlan:
    """Build a minimal CompiledRunPlan with one perceive phase node."""
    from lca.contracts.protocols.declarative.declarative_graph import (
        CognitivePhaseGraphPlan,
        PhaseBinding,
        PhaseNode,
        ValidationReport,
    )

    phase_node = PhaseNode(
        id="perceive.main",
        semantic_phase=SemanticPhase.PERCEIVE,
        binding="phase.test.recording",
        max_visits=1,
        terminal=False,
        execution_policy=PhaseExecutionPolicy(),
    )
    phase_graph = CognitivePhaseGraphPlan(
        entry=phase_node.id,
        nodes=(phase_node,),
        edges=(),
    )
    phase_binding = PhaseBinding(
        node_id=phase_node.id,
        semantic_phase=SemanticPhase.PERCEIVE,
        executor_capability="phase.test.recording",
        contributions=(),
    )
    return CompiledRunPlan(
        profile_path="test://wrap-instrument-contract",
        capability=cast(
            "Any",
            SimpleNamespace(profile_path="test://wrap-instrument-contract"),
        ),
        scope=cast(
            "Any",
            SimpleNamespace(profile_path="test://wrap-instrument-contract"),
        ),
        phase_graph=phase_graph,
        phase_bindings=(phase_binding,),
        validation_report=ValidationReport(issues=()),
    )


def test_assembler_wraps_with_instrument() -> None:
    """Every ``ExecutableNode.executor.execute`` must carry instrument markers."""
    plan = _compile_single_node_plan()
    scope = MappingRestrictedScope(capabilities={"phase.test.recording": _RecordingExecutor()})
    executable = GraphAssembler().assemble(plan, scope)

    assert "perceive.main" in executable.nodes
    node = executable.nodes["perceive.main"]
    assert isinstance(node, ExecutableNode)
    runnable = node.executor.execute
    assert getattr(runnable, WRAP_INSTRUMENTED_ATTR, False) is True, (
        f"node {node.node_id!r} executor is missing {WRAP_INSTRUMENTED_ATTR}"
    )
    assert getattr(runnable, "wrap_provenance", None) == ASSEMBLER_PROVENANCE, (
        f"node {node.node_id!r} executor wrap_provenance is not {ASSEMBLER_PROVENANCE!r}"
    )


def test_wrap_instrument_direct_marks_callable() -> None:
    """``wrap_instrument`` marks its wrapper synchronously without invoking it."""

    def sample(*args, **kwargs):
        return args, kwargs

    wrapped = wrap_instrument(sample)

    assert getattr(wrapped, WRAP_INSTRUMENTED_ATTR, False) is True
    assert getattr(wrapped, "wrap_provenance", None) == ASSEMBLER_PROVENANCE
    assert getattr(wrapped, "__wrapped__", None) is sample
