"""NodeGraphDriver (ADR-0218 §3.5 Composite) — v2 plan scheduler.

Forked from ``lca/harness/graph/execute/v2/node_graph_driver.py`` and
extended to:

- accept a required ``channel: PhaseOutputChannel`` parameter on
  ``run()``;
- project the terminal port_values into a :class:`PhaseOutput` and
  publish it on the channel;
- expose the projected output on ``InterpretationResult.output`` so the
  outer :class:`SubgraphRunner` can forward it.

The driver does **one** thing: walk yaml edges and run nodes until
termination. Responsibility split:

- scheduling loop          — this class
- executor resolution      — delegated to ``self._scope.resolve_factory``
  (the ``SubgraphRuntime`` seam)
- ``NodeContext`` assembly — delegated to ``build_node_context``
- ``NodeOutput`` → phase_result projection — delegated to
  ``project_node_output``
- edge selection           — delegated to ``select_edge``
- terminal signal publish  — delegated to
  ``project_port_values_to_phase_output`` + ``channel.publish``

D5 consumer: :class:`SubgraphRunner` (one ``.run()`` per think
subgraph execution).

Boundaries:
- does not import the outer drive / interpreter internals;
- does not mutate outer ``AgentState`` directly (emits facts only);
- does not call the Reducer or write the Spine (only produces
  ``PhaseVisit`` / ``RunFact`` for the existing commit path).
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from lca.contracts.exceptions.subgraph import (
    SubgraphCycleError,
    SubgraphDepthExceededError,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphNode,
    BundleGraphSpec,
    FactoryResolutionError,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    SemanticPhase,
)
from lca.framework.subgraph.plugins.channel import (
    PhaseOutput,
    PhaseOutputChannel,
)
from lca.framework.subgraph.plugins.driver_signal import (
    project_port_values_to_phase_output,
)
from lca.harness.declarative.execute.outcome_projection import (
    InterpretationResult,
    PhaseVisit,
)
from lca.harness.graph.execute.v2._port_context import PortContext
from lca.harness.graph.execute.v2.edge_selector import select_edge
from lca.harness.graph.execute.v2.node_context_factory import build_node_context
from lca.harness.graph.execute.v2.node_output_projector import (
    project_node_output as _project_node_output,
)
from lca.harness.graph.execute.v2.node_output_projector import (
    schema_from_node_config,
)

MAX_SUBGRAPH_DEPTH_DEFAULT = 8
ObserverFn = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class _ResolvedNode:
    """driver 内部用的扁平节点视图(spec.nodes + 按 id 索引)。"""

    node: BundleGraphNode
    index: int


class NodeGraphDriver:
    """v2 plan 调度循环。

    主循环(伪代码):
        current = spec.entry_node()
        port_context.set_outer_input(outer_input)
        visits = []
        while True:
            n = nodes[current]
            executor = scope.resolve_factory(n.factory, region)
            ctx = build_node_context(n, plan_ref, outer_state, scope)
            inp = port_context.build_input(n.inputs)
            out = await executor.node_execute(ctx, inp)
            phase_result = _project_node_output(out, schema_from_node_config(n.config))
            observers.map(o -> o("phase_graph.node.start", {...}))
            observers.map(o -> o("phase_graph.node.end", {...}))
            visits.append(PhaseVisit(current, THINK, phase_result.result_kind, None))
            port_context.merge_output(out.port_values)
            edge = select_edge(current_node_id=current, edges, phase_result, artifacts)
            if edge is None:
                output = project_port_values_to_phase_output(port_context._ports)
                channel.publish(producer_node=current, phase=region_phase, output=output)
                break
            current = edge.target
        return InterpretationResult(state=outer_state, output=output, ...)
    """

    def __init__(
        self,
        *,
        spec: BundleGraphSpec,
        plan_ref: str,
        scope: Any,  # SubgraphRuntime:有 .resolve/.resolve_factory 的对象
        region_phase: SemanticPhase = SemanticPhase.THINK,
        observers: tuple[ObserverFn, ...] = (),
        max_subgraph_depth: int = MAX_SUBGRAPH_DEPTH_DEFAULT,
    ) -> None:
        self._spec = spec
        self._plan_ref = plan_ref
        self._scope = scope
        self._region_phase = region_phase
        self._observers = observers
        self.max_subgraph_depth = max_subgraph_depth
        self._recursion_stack: set[str] = set()
        self._nodes_by_id: dict[str, BundleGraphNode] = {n.id: n for n in spec.nodes}
        # entry:yaml 显式声明优先;否则 fallback 到 nodes 列表的第一个节点。
        if spec.entry is None:
            if not spec.nodes:
                raise ValueError(f"BundleGraphSpec[{spec.id!r}] has no nodes and no entry")
            self._entry = spec.nodes[0].id
        else:
            if spec.entry not in self._nodes_by_id:
                raise ValueError(f"BundleGraphSpec[{spec.id!r}].entry {spec.entry!r} not in nodes")
            self._entry = spec.entry

    async def run(
        self,
        *,
        outer_state: AgentState,
        channel: PhaseOutputChannel,
        artifacts: Mapping[str, object],
        outer_input: Mapping[str, Any] | None = None,
    ) -> InterpretationResult:
        """跑 v2 plan,返回 InterpretationResult(与 _drive 同形)。

        ``channel`` is required: at termination the driver projects the
        collected ``port_values`` into a :class:`PhaseOutput` and
        publishes it. ``outer_input`` is the optional initial
        ``port_values`` projection from the outer drive.
        """
        visits: list[PhaseVisit] = []
        facts: list[Any] = []
        port_context = PortContext()
        if outer_input is not None:
            port_context.set_outer_input(outer_input)

        current_id = self._entry
        terminal_node = current_id
        output: PhaseOutput = PhaseOutput()

        while True:
            node = self._nodes_by_id[current_id]
            try:
                executor = self._scope.resolve_factory(node.factory, node.region)
            except FactoryResolutionError as exc:
                # fail-loud:registry 无法解析 → 返回 FAILED outcome
                return _failed_result(
                    plan_ref=self._plan_ref,
                    outer_state=outer_state,
                    node_id=current_id,
                    error=exc,
                    visits=tuple(visits),
                    facts=tuple(facts),
                    output=output,
                )

            ctx = build_node_context(
                node=node,
                plan_ref=self._plan_ref,
                outer_state=outer_state,
                scope=self._scope,
            )
            inp = port_context.build_input(node.inputs)

            try:
                out = await executor.node_execute(ctx, inp)
            except Exception as exc:
                return _failed_result(
                    plan_ref=self._plan_ref,
                    outer_state=outer_state,
                    node_id=current_id,
                    error=exc,
                    visits=tuple(visits),
                    facts=tuple(facts),
                    output=output,
                )

            schema = schema_from_node_config(node.config)
            phase_result = _project_node_output(out, schema)
            facts.extend(phase_result.facts)

            # 观察面 emit(framework 复用 EP,不引入新词表)
            await _emit_observers(
                self._observers,
                "phase_graph.node.start",
                {
                    "plan_ref": self._plan_ref,
                    "node_id": current_id,
                    "purpose": node.purpose,
                },
            )
            await _emit_observers(
                self._observers,
                "phase_graph.node.end",
                {
                    "plan_ref": self._plan_ref,
                    "node_id": current_id,
                    "purpose": node.purpose,
                    "result_kind": phase_result.result_kind,
                },
            )

            visits.append(
                PhaseVisit(current_id, SemanticPhase.THINK, phase_result.result_kind, None)
            )

            # merge output → 下一节点可读
            port_context.merge_output(out.port_values)

            edge = select_edge(
                current_node_id=current_id,
                edges=self._spec.edges,
                last_phase_result=phase_result,
                artifacts=artifacts,
            )
            if edge is None:
                # 终止:project port_values → PhaseOutput → channel publish
                terminal_node = current_id
                output = project_port_values_to_phase_output(port_context._ports)
                channel.publish(
                    producer_node=terminal_node,
                    phase=self._region_phase.value,
                    output=output,
                )
                break
            current_id = edge.target

        return InterpretationResult(
            state=outer_state,
            artifact=None,
            visits=tuple(visits),
            facts=tuple(facts),
            terminal_node=terminal_node,
            outcome=None,
            output=output,
        )

    async def _drive_subgraph_ref(
        self,
        ref: Any,
        outer_state: AgentState,
        depth: int = 0,
    ) -> AgentState:
        """Guard recursion into a nested ``sub_spec_ref``.

        Per ADR-0217 §3.3.1: depth is a soft limit (default 8). Cycle
        detection uses the same ``plan_ref`` appearing twice on the
        recursion stack. The guards fire *before* any inner execution;
        ``try/finally`` guarantees the stack is unwound on either
        success or failure.

        The recursion body itself is reserved for the v1 PR-3 follow-up
        (the resolver seam that resolves ``ref.plan_ref`` into a v2
        BundleGraphSpec and re-enters :meth:`run`). Until then, this
        method establishes the guards + state machine and delegates
        the actual inner execution to ``_drive_subgraph_inner`` (a
        thin seam the v1 PR-3 commit will wire up).

        Raises:
            SubgraphDepthExceededError: PG-007-depth
            SubgraphCycleError: PG-007-cycle
        """
        if depth > self.max_subgraph_depth:
            raise SubgraphDepthExceededError(depth, self.max_subgraph_depth)
        if ref.plan_ref in self._recursion_stack:
            raise SubgraphCycleError(ref.plan_ref)
        self._recursion_stack.add(ref.plan_ref)
        try:
            return await self._drive_subgraph_inner(ref, outer_state, depth)
        finally:
            self._recursion_stack.discard(ref.plan_ref)

    async def _drive_subgraph_inner(
        self,
        ref: Any,
        outer_state: AgentState,
        depth: int,
    ) -> AgentState:
        """Resolved recursion body for :meth:`_drive_subgraph_ref`.

        PR-3 will swap this for: resolve ``ref.plan_ref`` via
        ``self._scope`` into a BundleGraphSpec, instantiate a nested
        ``NodeGraphDriver``, and call ``run()`` with port passthrough.

        For PR-1 we just return ``outer_state`` so the recursion guards
        are observable in isolation (cycle/depth tests); the no-op
        body is intentional and documented in §2.1.2 of
        ``docs/specs/2026-09-10-nested-bundle-graph-spec.md``.
        """
        del ref, depth
        return outer_state


async def _emit_observers(
    observers: tuple[ObserverFn, ...],
    event_name: str,
    payload: dict[str, Any],
) -> None:
    """emit 给所有 observer。observer 失败 contained,不回滚(observer 是观察面)。"""
    for obs in observers:
        with contextlib.suppress(Exception):
            await obs(event_name, payload)


def _failed_result(
    *,
    plan_ref: str,
    outer_state: AgentState,
    node_id: str,
    error: BaseException,
    visits: tuple[PhaseVisit, ...],
    facts: tuple[Any, ...],
    output: PhaseOutput,
) -> InterpretationResult:
    """构造失败 outcome(与 _drive 失败语义对齐)。"""
    from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
        DeclarativeRunOutcome,
        ExecutionOutcome,
        PhaseRunCursor,
    )

    cursor = PhaseRunCursor(
        plan_ref=plan_ref,
        node_id=node_id,
        visit_counts=(),
        edge_counts=(),
        artifacts={},
        causation_refs=(),
        budget_snapshot={"step": 0},
    )
    from lca.contracts.models.core.policy.stop import StopDecision, StopReason
    outcome = DeclarativeRunOutcome(
        kind=ExecutionOutcome.FAILED,
        cursor=cursor,
        stop=StopDecision(should_stop=True, reason=StopReason.ERROR),
        error_fact=None,
    )
    return InterpretationResult(
        state=outer_state,
        artifact=None,
        visits=visits,
        facts=facts,
        terminal_node=node_id,
        outcome=outcome,
        output=output,
    )


__all__ = ["NodeGraphDriver", "ObserverFn"]
