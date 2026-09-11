"""NodeExecutorStrategy — wraps a :class:`NodeExecutor` as a graph strategy.

A :class:`NodeExecutor` is the ``think`` subgraph node contract:
``semantic_name: str``, ``declared_inputs: tuple[PortName, ...]``,
``declared_outputs: tuple[PortName, ...]``, ``async def execute(ctx,
input) -> output``. The strategy adapts the new graph kernel's
:class:`NodeInput` / :class:`NodeOutput` to that contract and uses the
executor lookup to resolve the right executor by semantic name.

The strategy trusts the kernel to enforce schema contracts:
``declared_inputs`` from the executor is the single source of truth for
which ports the executor will read; the strategy does not inspect the
``NodeIOSchema`` to recompute it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext as LegacyNodeContext,
    NodeExecutor,
    NodeInput as LegacyNodeInput,
    NodeOutput as LegacyNodeOutput,
)
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.ports import PortName
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.framework.graph.strategy_registry import (
    PhaseExecutorLookup,
    register_strategy,
    resolve_executor,
)


@dataclass(frozen=True, slots=True)
class NodeExecutorStrategy(NodeStrategy):
    """Wraps a :class:`NodeExecutor` (think subgraph node) as a graph strategy."""

    kind: BindingKind = BindingKind.NODE_EXECUTOR
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    executor_lookup: PhaseExecutorLookup | None = None

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        executor = resolve_executor(
            self.executor_lookup,
            binding=self.kind,
            node_id=context.node_id,
            region=None,
        )
        legacy_ctx = LegacyNodeContext(
            runtime=context.node_config.get("runtime", {}),
            budget=context.node_config.get("budget", {}),
            metadata={
                "plan_ref": context.plan_ref,
                "node_id": context.node_id,
                "binding_kind": context.binding_kind.value,
                "chain": context.chain,
            },
        )
        legacy_input = LegacyNodeInput(
            port_values=dict(input.port_values),
        )
        legacy_output: LegacyNodeOutput = await executor.execute(
            legacy_ctx, legacy_input
        )
        return NodeOutput(
            port_values=dict(legacy_output.port_values),
            next_hint=legacy_output.next_hint,
            producer_node=context.node_id,
        )


register_strategy(NodeExecutorStrategy())


__all__ = ["NodeExecutorStrategy"]