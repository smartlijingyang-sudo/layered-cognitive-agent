"""SubgraphStrategy — thin dispatcher over :class:`SubgraphRun`.

Architecture review C3: nested-run policy lives in
:mod:`lca.framework.graph.strategies.subgraph_run`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeInput, NodeIOSchema, NodeOutput
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.framework.graph.observation import GraphObserver, NullGraphObserver
from lca.framework.graph.strategies.subgraph_run import (
    DefaultSubgraphRun,
    RecursiveRunner,
    SubgraphRun,
    _load_subgraph_plan,
    _outer_declared_outputs,
    _repo_root,
)
from lca.framework.graph.strategy_registry import register_strategy


@dataclass(frozen=True, slots=True)
class SubgraphStrategy(NodeStrategy):
    kind: BindingKind = BindingKind.SUBGRAPH
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    recursive_runner: RecursiveRunner | None = None
    max_depth: int = 4
    depth_counter: Callable[[], int] | None = None
    observer: GraphObserver = field(default_factory=NullGraphObserver)
    clock: Callable[[], int] | None = None
    nested_run: SubgraphRun | None = None

    async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
        runner = self.nested_run
        if runner is None:
            if self.recursive_runner is None:
                raise RuntimeError(
                    "SubgraphStrategy.execute called without recursive_runner; "
                    "the host must inject one (typically the kernel-native "
                    "recursive PlanInterpreter.run closure)"
                )
            runner = DefaultSubgraphRun(
                recursive_runner=self.recursive_runner,
                max_depth=self.max_depth,
                depth_counter=self.depth_counter,
                observer=self.observer,
                clock=self.clock,
            )
        return await runner.run(context, input)


register_strategy(SubgraphStrategy())

__all__ = ["DefaultSubgraphRun", "RecursiveRunner", "SubgraphRun", "SubgraphStrategy"]
