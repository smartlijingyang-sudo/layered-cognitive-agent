"""ADR-0214 §6 PR-C: ``PhaseTraversal.advance`` terminal_predicate 路径行为契约。

锁定五条核心不变量:
1. ``terminal_predicate``/``predicate_registry``/``on_terminal`` 缺省 → 老行为不变。
2. terminal_predicate 不满足 → 正常 advance 到 edge.target。
3. terminal_predicate 满足 → 调用 on_terminal, **不** advance。
4. terminal_predicate 满足 + target 是 stop.main → 走 on_terminal 强制路由到 stop。
5. terminal_predicate 未注册 → 抛 PG-007(注册表漏配,显式失败)。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    LoopGuard,
    PhaseNode,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    DeclarativeValidationError,
    PhaseEdge,
    PhaseInput,
)
from lca.harness.graph.traversal import PhaseTraversal


def _make_traversal(node_id: str = "perceive.main") -> PhaseTraversal:
    return PhaseTraversal.start(
        plan_ref="test-plan",
        entry_node_id=node_id,
        artifacts=None,
        input=PhaseInput(),
    )


def _make_edge(source: str, target: str) -> PhaseEdge:
    return PhaseEdge(source=source, target=target, when="true")


def _make_target(node_id: str, terminal_predicate: str | None = None) -> PhaseNode:
    return PhaseNode(
        id=node_id,
        semantic_phase=SemanticPhase.THINK if node_id != "stop.main" else SemanticPhase.STOP,
        binding=f"phase.{node_id}.standard",
        max_visits=1,
        terminal=(node_id == "stop.main"),
        terminal_predicate=terminal_predicate,
    )


class _PredicateRegistry:
    """Minimal callable registry for terminal_predicate name → predicate."""

    def __init__(self, mapping: dict[str, Callable[[PhaseTraversal], bool]] | None = None) -> None:
        self._mapping = dict(mapping or {})

    def __call__(self, name: str) -> Callable[[PhaseTraversal], bool] | None:
        return self._mapping.get(name)


def test_advance_without_predicate_registry_preserves_historical_behavior() -> None:
    """不传 ``target_node``/``predicate_registry``/``on_terminal`` → 老行为(锁回归)。"""
    traversal = _make_traversal(node_id="perceive.main")
    edge = _make_edge("perceive.main", "think.main")
    traversal.advance(edge=edge, payload=None, causation_refs=())
    assert traversal.current_node_id == "think.main"


def test_advance_target_node_without_terminal_predicate_advances_normally() -> None:
    """target 有 terminal_predicate=None → 仍然 advance(锁 PG-007 三件套可选性)。"""
    traversal = _make_traversal(node_id="perceive.main")
    edge = _make_edge("perceive.main", "think.main")
    target = _make_target("think.main", terminal_predicate=None)
    registry = _PredicateRegistry()
    traversal.advance(
        edge=edge,
        payload=None,
        causation_refs=(),
        target_node=target,
        predicate_registry=registry,
    )
    assert traversal.current_node_id == "think.main"


def test_advance_terminal_predicate_unsatisfied_advances_normally() -> None:
    """terminal_predicate 满足但未到 → 仍 advance 到 edge.target。"""
    traversal = _make_traversal(node_id="perceive.main")
    edge = _make_edge("perceive.main", "think.main")
    target = _make_target("think.main", terminal_predicate="never_triggers")
    registry = _PredicateRegistry({"never_triggers": lambda _t: False})
    on_terminal_called: list[bool] = []

    def on_terminal() -> None:
        on_terminal_called.append(True)

    traversal.advance(
        edge=edge,
        payload=None,
        causation_refs=(),
        target_node=target,
        predicate_registry=registry,
        on_terminal=on_terminal,
    )
    assert traversal.current_node_id == "think.main"
    assert on_terminal_called == []


def test_advance_terminal_predicate_satisfied_invokes_on_terminal_and_skips_advance() -> None:
    """terminal_predicate 满足 → on_terminal 被调, current_node_id 不变。"""
    traversal = _make_traversal(node_id="perceive.main")
    edge = _make_edge("perceive.main", "think.main")
    target = _make_target("think.main", terminal_predicate="context_complete")
    registry = _PredicateRegistry({"context_complete": lambda _t: True})
    on_terminal_calls: list[int] = []

    def on_terminal() -> None:
        on_terminal_calls.append(1)

    traversal.advance(
        edge=edge,
        payload=None,
        causation_refs=(),
        target_node=target,
        predicate_registry=registry,
        on_terminal=on_terminal,
    )
    assert on_terminal_calls == [1]
    assert traversal.current_node_id == "perceive.main"  # 没 advance


def test_advance_terminal_predicate_routes_to_stop_main() -> None:
    """``on_terminal`` 内部将 current_node_id 切到 stop.main(模拟 PR-C 强制路由)。"""
    traversal = _make_traversal(node_id="perceive.main")
    edge = _make_edge("perceive.main", "think.main")
    target = _make_target("think.main", terminal_predicate="context_complete")
    registry = _PredicateRegistry({"context_complete": lambda _t: True})

    def force_to_stop() -> None:
        traversal.current_node_id = "stop.main"

    traversal.advance(
        edge=edge,
        payload=None,
        causation_refs=(),
        target_node=target,
        predicate_registry=registry,
        on_terminal=force_to_stop,
    )
    assert traversal.current_node_id == "stop.main"


def test_advance_terminal_predicate_unregistered_raises_pg_007() -> None:
    """terminal_predicate 名字没注册 → 显式 PG-007(防漏配)。"""
    traversal = _make_traversal(node_id="perceive.main")
    edge = _make_edge("perceive.main", "think.main")
    target = _make_target("think.main", terminal_predicate="does_not_exist")
    registry = _PredicateRegistry()  # empty

    with pytest.raises(DeclarativeValidationError) as exc_info:
        traversal.advance(
            edge=edge,
            payload=None,
            causation_refs=(),
            target_node=target,
            predicate_registry=registry,
        )
    assert exc_info.value.code == "PG-007"
    assert "does_not_exist" in str(exc_info.value)


def test_advance_terminal_predicate_satisfied_without_on_terminal_is_safe() -> None:
    """``on_terminal=None`` 时仍跳过 advance(无副作用 = 安全降级)。"""
    traversal = _make_traversal(node_id="perceive.main")
    edge = _make_edge("perceive.main", "think.main")
    target = _make_target("think.main", terminal_predicate="context_complete")
    registry = _PredicateRegistry({"context_complete": lambda _t: True})

    traversal.advance(
        edge=edge,
        payload=None,
        causation_refs=(),
        target_node=target,
        predicate_registry=registry,
        on_terminal=None,
    )
    # 没 advance + 没崩 = 优雅降级
    assert traversal.current_node_id == "perceive.main"


def test_advance_terminal_predicate_satisfied_still_enforces_edge_budget_first() -> None:
    """terminal_predicate 满足也不能豁免 edge.loop.max_iterations 硬截止。"""
    traversal = _make_traversal(node_id="perceive.main")
    looping_edge = PhaseEdge(
        source="perceive.main",
        target="think.main",
        when="true",
        loop=LoopGuard(max_iterations=1, budget="run.steps", terminal_predicate="false"),
    )
    target = _make_target("think.main", terminal_predicate="context_complete")
    registry = _PredicateRegistry({"context_complete": lambda _t: True})

    # edge loop 跑到 max_iterations=1, 第二次 advance 触发 PG-007 优先级
    # 高于 terminal_predicate (边预算检查在前)
    traversal.advance(
        edge=looping_edge,
        payload=None,
        causation_refs=(),
        target_node=target,
        predicate_registry=registry,
    )
    with pytest.raises(DeclarativeValidationError) as exc_info:
        traversal.advance(
            edge=looping_edge,
            payload=None,
            causation_refs=(),
            target_node=target,
            predicate_registry=registry,
        )
    assert exc_info.value.code == "PG-007"
    assert "loop edge budget" in str(exc_info.value)


@dataclass
class _Adder:
    """Side-effect probe to confirm on_terminal actually mutates state."""

    count: int = 0

    def hook(self) -> None:
        self.count += 1


def test_advance_terminal_predicate_only_invokes_on_terminal_once_per_call() -> None:
    """同一 advance 调用不会反复触发 on_terminal(一次预测一次结果)。"""
    traversal = _make_traversal(node_id="perceive.main")
    edge = _make_edge("perceive.main", "think.main")
    target = _make_target("think.main", terminal_predicate="context_complete")
    registry = _PredicateRegistry({"context_complete": lambda _t: True})
    adder = _Adder()

    traversal.advance(
        edge=edge,
        payload=None,
        causation_refs=(),
        target_node=target,
        predicate_registry=registry,
        on_terminal=adder.hook,
    )
    assert adder.count == 1
