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
termination. Per ADR-0219 §6 the recursion guards
(``SubgraphCycleError`` / ``SubgraphDepthExceededError``) and the
failure-result constructor (``_failed_result``) were moved out of
this module into :mod:`lca.framework.subgraph.plugins.runner`.
Responsibility split:

- scheduling loop          — this class
- executor resolution      — delegated to ``self._scope.resolve_factory``
  (the ``SubgraphRuntime`` seam)
- ``NodeContext`` assembly — delegated to ``build_node_context``
- ``NodeOutput`` → phase_result projection — delegated to
  ``project_node_output``
- edge selection           — delegated to ``select_edge``
- terminal signal publish  — delegated to
  ``project_port_values_to_phase_output`` + ``channel.publish``
- recursion guards         — delegated to :class:`SubgraphRunner`
- failure ``InterpretationResult`` shape — delegated to
  :func:`lca.framework.subgraph.plugins.runner._failed_result`

D5 consumer: :class:`SubgraphRunner` (one ``.run()`` per think
subgraph execution).

Boundaries:
- does not import the outer drive / interpreter internals;
- does not mutate outer ``AgentState`` directly (emits facts only);
- does not call the Reducer or write the Spine (only produces
  ``PhaseVisit`` / ``RunFact`` for the existing commit path);
- does not own cycle / depth guards (those live on the runner).
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from typing import Any

from lca.cognition.close_out import CognitiveCloseOut
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphNode,
    BundleGraphSpec,
    FactoryResolutionError,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    ExecutionOutcome,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseResult as _PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    SemanticPhase,
)
from lca.contracts.subgraph import SubgraphCloseOut
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
from lca.harness.graph.execute.v2._port_context import PortRegistry
from lca.harness.graph.execute.v2.edge_selector import select_edge
from lca.harness.graph.execute.v2.node_context_factory import build_node_context
from lca.harness.graph.execute.v2.node_output_projector import (
    project_node_output as _project_node_output,
)
from lca.harness.graph.execute.v2.node_output_projector import (
    schema_from_node_config,
)
from lca.loop.emit.node_emitter import emit_for_node, emit_reasoner_meta_for_node

_log = logging.getLogger(__name__)

MAX_SUBGRAPH_DEPTH_DEFAULT = 8
ObserverFn = Callable[[str, dict[str, Any]], Awaitable[None]]


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
            inp = port_context.build_input(getattr(executor, "declared_inputs", ()))
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
        sub_runner: Any | None = None,
        channel_factory: Callable[[], PhaseOutputChannel] | None = None,
        close_out: SubgraphCloseOut | None = None,
    ) -> None:
        self._spec = spec
        self._plan_ref = plan_ref
        self._scope = scope
        self._region_phase = region_phase
        self._observers = observers
        # ADR-0219 §10.11 item (1): inner recursion plumbing. Both are
        # populated by ``SubgraphRunner`` itself (which constructs the
        # driver), never by an external caller. A direct driver
        # construction that hits a ``sub_spec_ref`` node without these
        # set returns a FAILED ``InterpretationResult`` (fail-loud).
        self._sub_runner = sub_runner
        self._channel_factory = channel_factory
        # ADR-0219 §10.11.5: close-out field set is owned by the
        # cognition layer; the driver only forwards the projected
        # mapping onto the outer port context. ``SubgraphRunner``
        # injects ``CognitiveCloseOut`` explicitly; a direct caller
        # (test) gets the framework default.
        self._close_out = close_out or CognitiveCloseOut()
        # 显式 region 优先,fallback 到 bundle.region。任何 node 解析后仍为
        # None → fail-loud,要求 yaml 在 node 或 bundle 层给出 region。
        self._nodes_by_id: dict[str, BundleGraphNode] = {}
        for n in spec.nodes:
            effective_region = n.region if n.region is not None else spec.region
            if not effective_region:
                raise ValueError(
                    f"BundleGraphSpec[{spec.id!r}].node[{n.id!r}] has no region "
                    "(set node.region or spec.region)"
                )
            self._nodes_by_id[n.id] = (
                n if n.region is not None else replace(n, region=effective_region)
            )
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
        # Lazy import:avoid runner <-> driver circular import. The runner
        # owns the canonical FAILED InterpretationResult shape (ADR-0219
        # §6); the driver only needs it on the failure paths.
        from lca.framework.subgraph.plugins.runner import _failed_result

        visits: list[PhaseVisit] = []
        facts: list[Any] = []
        port_context = PortRegistry()
        if outer_input is not None:
            port_context.set_outer_input(outer_input)

        current_id = self._entry
        terminal_node = current_id
        output: PhaseOutput = PhaseOutput()

        while True:
            node = self._nodes_by_id[current_id]
            # ADR-0219 §10.11 item (1): inner recursion delegation. When the
            # current node has a typed sub_spec_ref, the driver delegates the
            # whole inner traversal to the injected SubgraphRunner, mirrors
            # the outer interpreter pattern (interpreter.py:402-414), and
            # advances via the normal edge-selection flow after folding.
            if getattr(node, "sub_spec_ref", None) is not None:
                if self._sub_runner is None or self._channel_factory is None:
                    return _failed_result(
                        plan_ref=self._plan_ref,
                        outer_state=outer_state,
                        node_id=current_id,
                        error=RuntimeError(
                            f"node {current_id!r} has sub_spec_ref but driver has "
                            "no sub_runner/channel_factory; sub_spec_ref requires "
                            "SubgraphRunner construction (ADR-0219 §10.11)"
                        ),
                        visits=tuple(visits),
                        facts=tuple(facts),
                        output=output,
                    )
                sub_runner = self._sub_runner
                sub_channel = self._channel_factory()
                _log.debug(
                    "node.subgraph_delegate plan_ref=%s node_id=%s sub_spec_ref=%s",
                    self._plan_ref,
                    current_id,
                    node.sub_spec_ref,
                )
                sub_state, sub_output = await sub_runner.run(
                    ref=node.sub_spec_ref,
                    outer_state=outer_state,
                    channel=sub_channel,
                )
                # mirror outer interpreter.py:402-414: absorb inner output
                # into port_context so subsequent edge nodes see it.
                sub_channel.absorb(sub_output)
                # ADR-0219 §10.11.5 close-out: project the inner
                # subgraph's per-node outputs through the injected
                # ``SubgraphCloseOut`` seam and forward the result onto
                # the outer port context. Field names live in the
                # cognition layer (``CLOSE_OUT_FIELDS``); the driver
                # does not enumerate them.
                inner_outputs = getattr(sub_channel, "_outputs", None) or {}
                projected = dict(self._close_out.project(inner_outputs))
                if projected:
                    port_context.set_outer_input(projected)
                # FAILED inner → propagate to outer driver via typed failure shape
                if sub_output.outcome_kind is ExecutionOutcome.FAILED:
                    return _failed_result(
                        plan_ref=self._plan_ref,
                        outer_state=sub_state,
                        node_id=current_id,
                        error=RuntimeError(sub_output.error or "inner subgraph failed"),
                        visits=tuple(visits),
                        facts=tuple(facts),
                        output=sub_output,
                    )
                outer_state = sub_state
                # emit observer for this node as if it were a single node exec
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
                        "result_kind": "subgraph",
                    },
                )
                visits.append(PhaseVisit(current_id, SemanticPhase.THINK, "subgraph", None))
                # Synthetic PhaseResult so select_edge runs against
                # self._spec.edges from current_id — the normal graph
                # semantics. binding_edge on the SubgraphReference is
                # advisory; the outer interpreter routes via the edge
                # D5 below.
                phase_result = _PhaseResult(result_kind="subgraph", payload=None)
                edge = select_edge(
                    current_node_id=current_id,
                    edges=self._spec.edges,
                    last_phase_result=phase_result,
                    artifacts=artifacts,
                )
                if edge is None:
                    terminal_node = current_id
                    output = sub_output
                    channel.publish(
                        producer_node=terminal_node,
                        phase=self._region_phase.value,
                        output=output,
                    )
                    break
                current_id = edge.target
                continue
            try:
                executor = self._scope.resolve_factory(node.factory, node.region)
            except FactoryResolutionError as exc:
                # fail-loud:registry 无法解析 → 返回 FAILED outcome
                # Fire observer start+end so the failure is visible in traces.
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
                        "result_kind": "failure",
                        "error": f"FactoryResolutionError: {exc}",
                    },
                )
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
            # ADR-0219 §5.5: driver reads port contract from the executor
            # instance (`executor.declared_inputs`), not from the graph node
            # (`node.inputs`). The graph only knows topology; the executor
            # owns its own typed port contract.
            declared_inputs = getattr(executor, "declared_inputs", ())
            inp = port_context.build_input(declared_inputs)

            # 观察面 emit: start fires before execution, end fires after
            # (both success and failure paths). Observer failures are
            # contained — observation never blocks execution.
            await _emit_observers(
                self._observers,
                "phase_graph.node.start",
                {
                    "plan_ref": self._plan_ref,
                    "node_id": current_id,
                    "purpose": node.purpose,
                },
            )

            try:
                out = await self._execute_with_emits(
                    executor=executor,
                    ctx=ctx,
                    node_input=inp,
                    node=node,
                    state=outer_state,
                )
            except Exception as exc:
                await _emit_observers(
                    self._observers,
                    "phase_graph.node.end",
                    {
                        "plan_ref": self._plan_ref,
                        "node_id": current_id,
                        "purpose": node.purpose,
                        "result_kind": "failure",
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
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

    async def _execute_with_emits(
        self,
        *,
        executor: Any,
        ctx: Any,
        node_input: Any,
        node: BundleGraphNode,
        state: AgentState,
    ) -> Any:
        """Wrap ``executor.node_execute`` with node-level EP dispatch (ADR-0217 §3.3.2).

        ``emit_on_enter`` EPs fire before the executor. On success,
        ``emit_on_exit`` EPs fire (with ``reasoner_meta`` routed to the
        special helper that reads ``turn_plan`` / ``turn_render`` from
        the input / output). On failure, ``reasoner_reason_end`` is
        emitted with ``outcome="failure"`` and the exception is
        re-raised so the existing failure path produces the FAILED
        ``InterpretationResult``. EP dispatch failures are contained
        (``contextlib.suppress`` inside the dispatcher) so observation
        never blocks execution.
        """
        for ep_id in node.config.get("emit_on_enter", ()):
            emit_for_node(ep_id, state)
        try:
            out = await executor.node_execute(ctx, node_input)
        except BaseException:
            for ep_id in node.config.get("emit_on_exit", ()):
                if ep_id == "reasoner_reason_end":
                    emit_for_node(ep_id, state, outcome="failure")
            raise
        for ep_id in node.config.get("emit_on_exit", ()):
            if ep_id == "reasoner_meta":
                plan = node_input.port_values.get("turn_plan")
                render = out.port_values.get("turn_render")
                if plan is not None and render is not None:
                    emit_reasoner_meta_for_node(state, plan, render)
            else:
                emit_for_node(ep_id, state)
        return out


async def _emit_observers(
    observers: tuple[ObserverFn, ...],
    event_name: str,
    payload: dict[str, Any],
) -> None:
    """emit 给所有 observer。observer 失败 contained,不回滚(observer 是观察面)。"""
    for obs in observers:
        with contextlib.suppress(Exception):
            await obs(event_name, payload)


__all__ = ["MAX_SUBGRAPH_DEPTH_DEFAULT", "NodeGraphDriver", "ObserverFn"]
