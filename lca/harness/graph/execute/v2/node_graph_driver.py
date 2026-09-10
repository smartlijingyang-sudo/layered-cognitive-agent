"""NodeGraphDriver (ADR-0218 §3.5 Composite)。

v2 plan 调度主循环。**只**做一件事——按 yaml edges 跑节点,直到终止。

职责分层:
  - 调度循环本身(本类)
  - executor 解析:委托 ``scope.resolve_factory``(SubgraphRuntime seam)
  - NodeContext 构造:委托 build_node_context(已有)
  - NodeOutput → PhaseResult 投影:委托 project_node_output(已有)
  - 边选择:委托 select_edge(已有)

D5 消费点:`interpreter._drive_subgraph_inner` v2 分支调一次 .run()。

边界:
  - 不感知 outer drive / interpreter 内部状态(scope 由 interpreter 注入)
  - 不直接改 outer AgentState(只 emit 事实,reducer 经既有路径 commit)
  - 不调 Reducer / 不写 Spine(只构造 PhaseVisit / RunFact 入 fact list)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphEdge,
    BundleGraphNode,
    BundleGraphSpec,
)
from lca.contracts.protocols.declarative.declarative_1.factory_resolver import (
    FactoryResolutionError,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    SemanticPhase,
)
from lca.harness.declarative.execute.outcome_projection import (
    InterpretationResult,
    PhaseVisit,
)
from lca.harness.graph.execute.v2._port_context import PortContext
from lca.harness.graph.execute.v2.edge_selector import select_edge
from lca.harness.graph.execute.v2.node_context_factory import build_node_context
from lca.harness.graph.execute.v2.node_output_projector import (
    schema_from_node_config,
)
from lca.harness.graph.execute.v2.node_output_projector import (
    project_node_output as _project_node_output,
)


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
                break
            current = edge.target
        return InterpretationResult(state=outer_state, visits=visits, ...)
    """

    def __init__(
        self,
        *,
        spec: BundleGraphSpec,
        plan_ref: str,
        scope: Any,  # SubgraphRuntime:有 .resolve/.resolve_factory 的对象
        observers: tuple[ObserverFn, ...] = (),
    ) -> None:
        self._spec = spec
        self._plan_ref = plan_ref
        self._scope = scope
        self._observers = observers
        self._nodes_by_id: dict[str, BundleGraphNode] = {n.id: n for n in spec.nodes}
        # entry:yaml 显式声明优先;否则 fallback 到 nodes 列表的第一个节点。
        if spec.entry is None:
            if not spec.nodes:
                raise ValueError(
                    f"BundleGraphSpec[{spec.id!r}] has no nodes and no entry"
                )
            self._entry = spec.nodes[0].id
        else:
            if spec.entry not in self._nodes_by_id:
                raise ValueError(
                    f"BundleGraphSpec[{spec.id!r}].entry {spec.entry!r} not in nodes"
                )
            self._entry = spec.entry

    async def run(
        self,
        *,
        outer_state: AgentState,
        artifacts: Mapping[str, object],
        outer_input: Mapping[str, Any] | None = None,
    ) -> InterpretationResult:
        """跑 v2 plan,返回 InterpretationResult(与 _drive 同形)。

        outer_input:从 outer drive 传入的初始 port_values(yaml 节点 inputs 投影用)。
        """
        visits: list[PhaseVisit] = []
        facts: list[Any] = []
        port_context = PortContext()
        if outer_input is not None:
            port_context.set_outer_input(outer_input)

        current_id = self._entry
        terminal_node = current_id

        while True:
            node = self._nodes_by_id[current_id]
            try:
                executor = self._scope.resolve_factory(node.factory, node.region)
            except FactoryResolutionError as exc:
                # fail-loud:runtime 无法解析 → 返回 FAILED outcome
                return _failed_result(
                    outer_state=outer_state,
                    node_id=current_id,
                    error=exc,
                    visits=tuple(visits),
                    facts=tuple(facts),
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
                    outer_state=outer_state,
                    node_id=current_id,
                    error=exc,
                    visits=tuple(visits),
                    facts=tuple(facts),
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
                # 终止
                terminal_node = current_id
                break
            current_id = edge.target

        return InterpretationResult(
            state=outer_state,
            artifact=None,
            visits=tuple(visits),
            facts=tuple(facts),
            terminal_node=terminal_node,
            outcome=None,
        )


async def _emit_observers(
    observers: tuple[ObserverFn, ...],
    event_name: str,
    payload: dict[str, Any],
) -> None:
    """emit 给所有 observer。observer 失败 contained,不回滚(observer 是观察面)。"""
    for obs in observers:
        try:
            await obs(event_name, payload)
        except Exception:
            # observer 失败 ignored,符合 C7 观察面不触发控制面
            pass


def _failed_result(
    *,
    outer_state: AgentState,
    node_id: str,
    error: BaseException,
    visits: tuple[PhaseVisit, ...],
    facts: tuple[Any, ...],
) -> InterpretationResult:
    """构造失败 outcome(与 _drive 失败语义对齐)。"""
    from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
        DeclarativeRunOutcome,
        ExecutionOutcome,
        PhaseRunCursor,
    )

    error_fact = f"{type(error).__name__}: {error}"
    cursor = PhaseRunCursor(node_id=node_id, step=0)
    outcome = DeclarativeRunOutcome(
        kind=ExecutionOutcome.FAILED,
        cursor=cursor,
        error_kind="internal",
        error_fact=error_fact,
    )
    return InterpretationResult(
        state=outer_state,
        artifact=None,
        visits=visits,
        facts=facts,
        terminal_node=node_id,
        outcome=outcome,
    )


__all__ = ["NodeGraphDriver", "ObserverFn"]
