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

Node-level ``emit_on_enter`` / ``emit_on_exit`` declarations under
``config.config`` (the yaml shape the lifter hands over) are forwarded
to :func:`lca.loop.emit.node_emitter.emit_for_node` before and after the
executor call. Driver dispatch is failure-contained so a misconfigured
EP does not abort the graph (ADR-0240 / Note `2026-09-15-node-emit-dispatcher-wiring`).
"""
from __future__ import annotations

import contextlib
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
    NodeExecutorLookup,
    register_strategy,
    resolve_executor,
)
from lca.loop.emit.node_emitter import emit_for_node


@dataclass(frozen=True, slots=True)
class NodeExecutorStrategy(NodeStrategy):
    """Wraps a :class:`NodeExecutor` (think subgraph node) as a graph strategy.

    ``executor_lookup`` resolves ``(binding=NODE_EXECUTOR, node_id=<factory>)``
    to the :class:`NodeExecutor` instance for that node. The map of
    factory name to instance is owned by the runtime closure that built
    this strategy — the framework never inspects business-layer
    factory names.

    ``node_runtime_view_factory`` builds the
    :class:`_NodeRuntimeView` so node plugins' ``context.runtime.<name>``
    reads route through the capability scope.
    """

    kind: BindingKind = BindingKind.NODE_EXECUTOR
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    executor_lookup: NodeExecutorLookup | None = None
    node_runtime_view_factory: Any = None

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        executor = resolve_executor(
            self.executor_lookup,
            binding=self.kind,
            node_id=context.node_id,
            region=None,
        )
        agent_state = dict(context.node_config or {}).get("agent_state")
        runtime = self._build_runtime(agent_state)
        legacy_ctx = LegacyNodeContext(
            runtime=runtime,
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
        # Think / cognition subgraph nodes implement
        # ``NodeExecutor.node_execute`` (legacy contract); some
        # test-only executors expose ``execute`` directly. Probe
        # both so the kernel does not couple to either name.
        executor_call = getattr(executor, "node_execute", None)
        if executor_call is None:
            executor_call = getattr(executor, "execute", None)
        if executor_call is None:
            raise RuntimeError(
                f"node executor {type(executor).__name__} exposes neither "
                "node_execute nor execute; cannot dispatch from kernel"
            )
        # Node-level emit dispatch (ADR-0240): the yaml `emit_on_enter`
        # list lives at `context.node_config["config"]["emit_on_enter"]`
        # after the lifter flattens the node dict. Fire each EP via the
        # dispatcher before invoking the executor. State may be absent
        # for non-subgraph nodes; the helpers dereference `state.trace_id`
        # so we skip dispatch when state is None.
        self._dispatch_node_emits(
            context.node_config, "emit_on_enter", agent_state
        )
        legacy_output: LegacyNodeOutput = await executor_call(
            legacy_ctx, legacy_input
        )
        self._dispatch_node_emits(
            context.node_config, "emit_on_exit", agent_state
        )
        # D4 cutover: pass-through only. The legacy NodeOutput carries
        # port_values (typed port store) and an optional next_hint (free-form
        # metadata). The kernel NodeOutput drops result_kind/next_hint/next_hints
        # — routing decisions now flow through the typed RoutingDecision port
        # in port_values. Plugins that need routing emit it directly.
        return NodeOutput(
            port_values=dict(legacy_output.port_values),
            producer_node=context.node_id,
        )

    def _build_runtime(self, agent_state: Any) -> Any:
        """Return a runtime view for ``context.runtime`` reads.

        When ``node_runtime_view_factory`` is wired, the factory
        returns a per-call :class:`_NodeRuntimeView` over the supplied
        ``agent_state`` and the runtime capability scope. When the
        factory is ``None`` (default singleton registered via
        :func:`register_strategy`), an empty dict is returned and node
        plugins that read ``context.runtime.<name>`` see ``None``
        (matching the legacy soft-fail path).
        """
        if self.node_runtime_view_factory is not None:
            return self.node_runtime_view_factory(agent_state)
        return {}

    @staticmethod
    def _dispatch_node_emits(
        node_config: Any, key: str, state: Any
    ) -> None:
        """Fire node-level ``emit_on_enter`` / ``emit_on_exit`` entries.

        Reads the list from ``node_config["config"][key]`` (the yaml
        shape the lifter hands over). Falls back to ``node_config[key]``
        for hand-built plans. A non-list value is treated as no-op;
        dispatcher failures are contained with
        :func:`contextlib.suppress` so a misconfigured EP does not
        abort the graph (ADR-0240 §Decision).
        """
        if not isinstance(node_config, dict):
            return
        emits: Any = None
        inner = node_config.get("config")
        if isinstance(inner, dict):
            emits = inner.get(key)
        if emits is None:
            emits = node_config.get(key)
        if not isinstance(emits, (list, tuple)):
            return
        for ep_id in emits:
            with contextlib.suppress(Exception):
                emit_for_node(ep_id, state)


register_strategy(NodeExecutorStrategy())


__all__ = ["NodeExecutorStrategy"]