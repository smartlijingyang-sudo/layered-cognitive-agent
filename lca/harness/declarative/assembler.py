"""ADR-0075 GraphAssembler：只解释已编译 binding，不选择业务实现。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from lca.contracts.protocols.declarative_phase_graph import (
    DeclarativeValidationError,
    PhaseContribution,
    PhaseExecutor,
)
from lca.contracts.protocols.plan import CompiledRunPlan


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
    executor_capability: str
    executor: PhaseExecutor
    contributions: tuple[ExecutableContribution, ...]


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
        if not plan.is_declarative:
            raise DeclarativeValidationError("PG-001", "CompiledRunPlan has no declarative phase graph")
        plan.validation_report.require_valid()
        nodes: dict[str, ExecutableNode] = {}
        for binding in plan.phase_bindings:
            try:
                executor = scope.resolve(binding.executor_capability)
            except KeyError as exc:
                raise DeclarativeValidationError(
                    "PS-002", f"missing assembled executor capability: {binding.executor_capability}"
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
                        "PS-002", f"missing assembled contribution capability: {contribution.executor}"
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
                executor_capability=binding.executor_capability,
                executor=executor,
                contributions=tuple(contributions),
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
