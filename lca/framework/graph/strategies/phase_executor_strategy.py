"""PhaseExecutorStrategy — wraps a :class:`PhaseExecutor` as a graph strategy.

The strategy is the single seam that turns a six-phase ``PhaseExecutor``
into a graph node. It calls a host-injected ``runner`` closure that
takes a :class:`PhaseInput` and returns a :class:`PhaseResult`.

Why the strategy does not build its own :class:`PhaseContext`:

Building a Protocol-conforming PhaseContext from scratch requires
non-trivial inputs (AgentState, JournalCommitter, Budget, capabilities,
results_by_phase) that the new kernel does not yet own. To keep this
PR self-contained, the strategy delegates context construction to a
``runner`` callable injected by the host — typically the existing
:class:`PhaseExecutionTransaction` setup. PR-4 (single visit
state machine) replaces this with a first-class context builder that
the kernel itself owns.

Production setup:

```python
def runner(inp: PhaseInput) -> PhaseResult:
    return transaction.run(...)

strategy = PhaseExecutorStrategy(
    runner=runner,
    port_for_result_kind=lambda r: r.result_kind,
)
```
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseInput,
    PhaseResult,
)
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.framework.graph.strategy_registry import register_strategy

PhaseRunner = Callable[[PhaseInput, StrategyContext], PhaseResult]
"""Host-injected closure that runs one phase visit.

The closure takes the strategy-provided :class:`PhaseInput` and the
:class:`StrategyContext`; it owns all context construction and
returns a :class:`PhaseResult`. In production this is the existing
:class:`lca.loop.transaction.PhaseExecutionTransaction.run` body.
"""


@dataclass(frozen=True, slots=True)
class PhaseExecutorStrategy(NodeStrategy):
    """Wraps a :class:`PhaseExecutor` as a graph strategy."""

    kind: BindingKind = BindingKind.PHASE_EXECUTOR
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    runner: PhaseRunner | None = None

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        if self.runner is None:
            raise RuntimeError(
                "PhaseExecutorStrategy.execute called without runner; "
                "the host must inject one (typically via PhaseExecutionTransaction)"
            )
        phase_input = PhaseInput(artifact=dict(input.port_values) or None)
        result: PhaseResult = self.runner(phase_input, context)
        return _project_phase_result(result, context.node_id)


def _project_phase_result(result: PhaseResult, node_id: str) -> NodeOutput:
    port_values: dict[str, Any] = {}
    if result.payload is not None:
        port_name = _port_for_result_kind(result.result_kind)
        port_values[port_name] = result.payload
    return NodeOutput(
        port_values=port_values,
        next_hint=result.next_hints.get("next_hint") if result.next_hints else None,
        producer_node=node_id,
    )


_KIND_TO_PORT = {
    "decision": "decision",
    "observation": "observation",
    "reflection": "reflection",
    "response": "response",
    "phase_error": "observation",
}


def _port_for_result_kind(result_kind: str) -> str:
    return _KIND_TO_PORT.get(result_kind, "response")


register_strategy(PhaseExecutorStrategy())


__all__ = ["PhaseExecutorStrategy", "PhaseRunner"]