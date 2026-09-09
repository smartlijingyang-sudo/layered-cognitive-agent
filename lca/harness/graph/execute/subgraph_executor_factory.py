"""Build ``ExecutablePlan`` instances for nested subgraph drives."""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.declarative.compile.assembler.assembler import (
    ExecutablePlan,
    GraphAssembler,
    MappingRestrictedScope,
)


def assemble_subgraph_executable(
    plan: CompiledRunPlan, scope: MappingRestrictedScope | None = None
) -> ExecutablePlan:
    """Assemble one subgraph ``ExecutablePlan``.

    When ``scope`` is provided, uses it directly. Otherwise creates an empty
    scope. The interpreter's scope-aware assembly path is preferred.
    """

    if scope is None:
        scope = MappingRestrictedScope({})
    return GraphAssembler().assemble(plan, scope)


def default_subgraph_executable_factory() -> Callable[[CompiledRunPlan], ExecutablePlan]:
    """Return the default subgraph ``ExecutablePlan`` builder."""

    return assemble_subgraph_executable


__all__ = [
    "assemble_subgraph_executable",
    "default_subgraph_executable_factory",
]
