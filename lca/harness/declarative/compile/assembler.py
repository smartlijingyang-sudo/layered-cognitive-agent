"""ADR-0075 GraphAssembler：只解释已编译 binding，不选择业务实现。

Every executor attached to an ``ExecutableNode`` is funneled through
:func:`wrap_instrument` so the spine Layer-3 invariant holds
(``node.executor.__lca_instrumented__`` is ``True`` and the wrapper's
``wrap_provenance`` is ``"assembler"``). ``assert_all_instrumented`` is the
build-time hard-fail that rejects any plan that escaped the assembler wrap.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from lca.contracts.protocols.declarative.declarative_fault_tolerance import PhaseExecutionPolicy
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeValidationError,
    PhaseContribution,
    PhaseExecutor,
    SemanticPhase,
)
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.declarative.compile.instrument_wrap import (
    ASSEMBLER_PROVENANCE,
    WRAP_INSTRUMENTED_ATTR,
    wrap_executor,
    wrap_instrument,  # noqa: F401  re-exported for tests and external wrap sites
)
from lca.harness.declarative.controls.validation import require_valid


@runtime_checkable
class RestrictedScope(Protocol):
    """Assembler 可见的最小 capability 查询面，不泄露 Cordis Context。"""

    def resolve(self, capability: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class MappingRestrictedScope:
    """测试和驱动可使用的只读 capability scope。"""

    capabilities: Mapping[str, Any]

    def resolve(self, capability: str) -> Any:
        if capability not in self.capabilities:
            raise KeyError(capability)
        return self.capabilities[capability]


@dataclass(frozen=True, slots=True)
class ExecutableContribution:
    declaration: PhaseContribution
    executor: PhaseExecutor


@dataclass(frozen=True, slots=True)
class ExecutableNode:
    node_id: str
    semantic_phase: SemanticPhase
    executor_capability: str
    executor: PhaseExecutor
    contributions: tuple[ExecutableContribution, ...]
    execution_policy: PhaseExecutionPolicy = field(default_factory=PhaseExecutionPolicy)


@dataclass(frozen=True, slots=True)
class ExecutablePlan:
    plan: CompiledRunPlan
    nodes: Mapping[str, ExecutableNode]


class UninstrumentedNode(Exception):
    """Raised when a phase graph node was not wrapped by the assembler.

    Carries ``plan_name`` and ``node_id`` so callers (CLI, diagnostics, CI
    failure reporters) can produce targeted messages without re-walking the
    plan to find the offending executor.
    """

    __slots__ = ("plan_name", "node_id")

    def __init__(self, plan_name: str, node_id: str) -> None:
        self.plan_name = plan_name
        self.node_id = node_id
        super().__init__(
            f"phase graph node {node_id!r} in plan {plan_name!r} is not "
            "wrapped by the assembler (missing "
            f"{WRAP_INSTRUMENTED_ATTR!r} or wrap_provenance "
            f"!= {ASSEMBLER_PROVENANCE!r})"
        )


def _resolve_runnable(executor: Any) -> Any:
    """Return the underlying callable the Layer-3 check should inspect.

    Production executors are ``InstrumentedPhaseExecutor`` instances, but
    hand-crafted or pre-existing test plans may attach a bare callable or a
    plain :class:`PhaseExecutor` object whose ``.execute`` is the actual
    runnable. The check looks at the same callable ``wrap_executor`` would.
    """

    if executor is None:
        return None
    execute = getattr(executor, "execute", None)
    if callable(execute):
        return execute
    if callable(executor):
        return executor
    return None


def assert_all_instrumented(plan: ExecutablePlan) -> None:
    """Hard-fail the plan if any node's runnable lacks the assembler wrap.

    Walks every node in the plan and asserts that the node's underlying
    runnable carries the Layer-3 invariants: ``__lca_instrumented__`` is
    truthy and ``wrap_provenance`` equals the constant
    :data:`ASSEMBLER_PROVENANCE` exported by :mod:`instrument_wrap`. The check
    is intentionally narrow — it does not invoke the runnable, it only looks
    at its marker attributes. A bare, hand-built plan triggers
    :class:`UninstrumentedNode`; production callers get a fail-fast error
    before the runtime ever calls the wrap site.

    Returns ``None`` on success so callers can use the function in pytest
    ``assert`` statements and in sequenced compile pipelines.
    """

    plan_name = plan.plan.profile_path
    for node_id, node in plan.nodes.items():
        runnable = _resolve_runnable(node.executor)
        if runnable is None:
            raise UninstrumentedNode(plan_name, node_id)
        if not getattr(runnable, WRAP_INSTRUMENTED_ATTR, False):
            raise UninstrumentedNode(plan_name, node_id)
        if getattr(runnable, "wrap_provenance", None) != ASSEMBLER_PROVENANCE:
            raise UninstrumentedNode(plan_name, node_id)
    return None


class GraphAssembler:
    """把 capability binding 装配成可执行 Protocol 实例。

    本类刻意不导入任一业务插件模块，亦不会根据 plugin ID、类名或 factory
    key 决定分支。所有实现都由 plan node 的 capability key 定位。
    """

    def assemble(self, plan: CompiledRunPlan, scope: RestrictedScope) -> ExecutablePlan:
        if plan.phase_graph is None or not plan.phase_bindings:
            raise DeclarativeValidationError(
                "PG-001", "CompiledRunPlan has no declarative phase graph"
            )
        require_valid(plan.validation_report)
        nodes: dict[str, ExecutableNode] = {}
        policies = {node.id: node.execution_policy for node in plan.phase_graph.nodes}
        for binding in plan.phase_bindings:
            execution_policy = policies.get(binding.node_id)
            if execution_policy is None:
                raise DeclarativeValidationError(
                    "PG-001", f"phase binding has no node execution policy: {binding.node_id}"
                )
            try:
                executor = scope.resolve(binding.executor_capability)
            except KeyError as exc:
                raise DeclarativeValidationError(
                    "PS-002",
                    f"missing assembled executor capability: {binding.executor_capability}",
                ) from exc
            if not isinstance(executor, PhaseExecutor):
                execute = getattr(executor, "execute", None)
                if not callable(execute):
                    raise DeclarativeValidationError(
                        "PS-002",
                        f"capability does not implement PhaseExecutor: {binding.executor_capability}",
                    )
            executor = wrap_executor(executor)
            contributions: list[ExecutableContribution] = []
            for contribution in binding.contributions:
                try:
                    contribution_executor = scope.resolve(contribution.executor)
                except KeyError as exc:
                    raise DeclarativeValidationError(
                        "PS-002",
                        f"missing assembled contribution capability: {contribution.executor}",
                    ) from exc
                execute = getattr(contribution_executor, "execute", None)
                if not callable(execute):
                    raise DeclarativeValidationError(
                        "PS-002",
                        f"contribution does not implement executable protocol: {contribution.executor}",
                    )
                contributions.append(
                    ExecutableContribution(
                        declaration=contribution,
                        executor=contribution_executor,
                    )
                )
            nodes[binding.node_id] = ExecutableNode(
                node_id=binding.node_id,
                semantic_phase=binding.semantic_phase,
                executor_capability=binding.executor_capability,
                executor=executor,
                contributions=tuple(contributions),
                execution_policy=execution_policy,
            )
        executable = ExecutablePlan(plan=plan, nodes=nodes)
        assert_all_instrumented(executable)
        return executable


__all__ = [
    "ExecutableContribution",
    "ExecutableNode",
    "ExecutablePlan",
    "GraphAssembler",
    "MappingRestrictedScope",
    "RestrictedScope",
    "UninstrumentedNode",
    "assert_all_instrumented",
    "wrap_instrument",
]
