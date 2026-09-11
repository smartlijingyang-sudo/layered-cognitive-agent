"""PhaseExecutorStrategy — wraps a :class:`PhaseExecutor` as a graph strategy.

The strategy is the single seam that turns a six-phase ``PhaseExecutor``
into a graph node. It calls a host-injected ``runner`` closure that
takes a :class:`PhaseInput` and a :class:`StrategyContext` and
returns a :class:`PhaseResult`. The runner may be sync or async;
the strategy awaits the result if it is awaitable.

Production setup (kernel-native, post
note 2026-09-11-kernel-native-phase-runner):

```python
async def runner(phase_input, strategy_ctx):
    executor = phase_executors[f"phase.{semantic}.standard"]
    context = RestrictedPhaseContext(...)
    return await executor.execute(context, phase_input)

strategy = PhaseExecutorStrategy(runner=runner)
```
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from inspect import isawaitable
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

PhaseRunner = Callable[[PhaseInput, StrategyContext], "PhaseResult | Awaitable[PhaseResult]"]
"""Host-injected closure that runs one phase visit.

The closure takes the strategy-provided :class:`PhaseInput` and the
:class:`StrategyContext`; it owns all context construction and
returns a :class:`PhaseResult` (sync) or an awaitable that resolves
to one (async). The strategy awaits the result if it is awaitable.
Production closures are async because :class:`PhaseExecutor.execute`
is async.
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
                "the host must inject one"
            )
        phase_input = PhaseInput(artifact=dict(input.port_values) or None)
        outcome = self.runner(phase_input, context)
        if isawaitable(outcome):
            outcome = await outcome
        result: PhaseResult = outcome  # type: ignore[assignment]
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
        result_kind=result.result_kind,
        next_hints=dict(result.next_hints) if result.next_hints else {},
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