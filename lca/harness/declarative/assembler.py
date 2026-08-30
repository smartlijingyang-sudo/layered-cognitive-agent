"""ADR-0075 GraphAssembler：只解释已编译 binding，不选择业务实现。"""

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
from lca.harness.declarative.validation import require_valid


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
        return ExecutablePlan(plan=plan, nodes=nodes)


__all__ = [
    "ExecutableContribution",
    "ExecutableNode",
    "ExecutablePlan",
    "GraphAssembler",
    "MappingRestrictedScope",
    "RestrictedScope",
]
