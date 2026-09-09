"""ADR-0214 §6 PR-C: ``PhaseTraversal.visit`` precondition 路径行为契约。

锁定五条核心不变量:
1. ``precondition=None`` → 历史行为完全不变(回归锁)。
2. precondition 满足 → visit 计入,返回 count(>=1)。
3. precondition 不满足 → visit **不**计入,返回 -1。
4. 多次不满足 + 一次满足 → visit_counts 仅在满足那次 +1。
5. precondition 在 max_visits 耗尽后仍不满足 → **不**抛 PG-007(因为未计入)。
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    DeclarativeValidationError,
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


class _Switch:
    """A predicate that flips True after N ``False`` evaluations."""

    def __init__(self, hold_for: int) -> None:
        self._hold_for = hold_for
        self.calls = 0

    def __call__(self, _t: PhaseTraversal) -> bool:
        self.calls += 1
        return self.calls > self._hold_for


def test_visit_without_precondition_preserves_historical_behavior() -> None:
    """``precondition=None`` → 老行为完全不变(锁回归)。"""
    traversal = _make_traversal()
    count = traversal.visit(node_id="perceive.main", max_visits=3)
    assert count == 1
    assert traversal.visit_counts["perceive.main"] == 1


def test_visit_without_precondition_still_raises_pg_007_on_overrun() -> None:
    """``precondition=None`` 且 count > max_visits → 抛 PG-007(锁回归)。"""
    traversal = _make_traversal()
    for _ in range(2):
        traversal.visit(node_id="perceive.main", max_visits=2)
    with pytest.raises(DeclarativeValidationError) as exc_info:
        traversal.visit(node_id="perceive.main", max_visits=2)
    assert exc_info.value.code == "PG-007"


def test_visit_with_satisfied_precondition_increments_count() -> None:
    """precondition 满足 → visit 计入,返回 count (>=1)。"""
    traversal = _make_traversal()
    count = traversal.visit(
        node_id="perceive.main",
        max_visits=3,
        precondition=lambda _t: True,
    )
    assert count == 1
    assert traversal.visit_counts["perceive.main"] == 1


def test_visit_with_unsatisfied_precondition_returns_minus_one() -> None:
    """precondition 不满足 → 返回 -1,visit_counts 不变。"""
    traversal = _make_traversal()
    count = traversal.visit(
        node_id="perceive.main",
        max_visits=3,
        precondition=lambda _t: False,
    )
    assert count == -1
    assert "perceive.main" not in traversal.visit_counts


def test_visit_with_unsatisfied_precondition_does_not_set_current_node() -> None:
    """precondition 不满足 → current_node_id 保持原值(未真正进入)。"""
    traversal = _make_traversal(node_id="perceive.main")
    original = traversal.current_node_id
    traversal.visit(
        node_id="think.main",
        max_visits=3,
        precondition=lambda _t: False,
    )
    assert traversal.current_node_id == original


def test_visit_counts_only_increment_on_satisfied_precondition() -> None:
    """多次不满足 + 一次满足 → visit_counts 只在满足那次 +1。"""
    pred = _Switch(hold_for=2)  # False, False, True
    traversal = _make_traversal()
    c1 = traversal.visit(node_id="perceive.main", max_visits=10, precondition=pred)
    c2 = traversal.visit(node_id="perceive.main", max_visits=10, precondition=pred)
    c3 = traversal.visit(node_id="perceive.main", max_visits=10, precondition=pred)
    assert c1 == -1
    assert c2 == -1
    assert c3 == 1
    assert traversal.visit_counts["perceive.main"] == 1


def test_visit_repeatedly_unsatisfied_precondition_never_raises_pg_007() -> None:
    """precondition 永不满足 → max_visits 永远不会耗尽 → 不抛 PG-007。

    这是 PR-C 的关键收益: precondition 把"无意义的硬截止"变成"重试到
    context 满足为止",而不是无脑 raise。
    """

    def always_false(_t: PhaseTraversal) -> bool:
        return False

    traversal = _make_traversal()
    # 尝试 100 次都失败;max_visits=2, 但 visit_counts 始终为 0
    for _ in range(100):
        count = traversal.visit(
            node_id="perceive.main",
            max_visits=2,
            precondition=always_false,
        )
        assert count == -1
    assert traversal.visit_counts == {}


def test_visit_satisfied_after_exhausted_max_visits_still_raises_pg_007() -> None:
    """进入计数已达 max_visits 后,即使 precondition 满足也抛 PG-007。

    这是关键对称性: precondition 只豁免"未计入"的访问;一旦满足并
    计入到上限,后续调用就是普通溢出。
    """
    traversal = _make_traversal()
    # 先满足 2 次,填满 max_visits=2
    traversal.visit(node_id="perceive.main", max_visits=2, precondition=lambda _t: True)
    traversal.visit(node_id="perceive.main", max_visits=2, precondition=lambda _t: True)
    # 第 3 次仍满足 → 应当 raise PG-007
    with pytest.raises(DeclarativeValidationError) as exc_info:
        traversal.visit(
            node_id="perceive.main",
            max_visits=2,
            precondition=lambda _t: True,
        )
    assert exc_info.value.code == "PG-007"


def test_visit_precondition_receives_self_traversal() -> None:
    """precondition 拿到的 PhaseTraversal 是当前 traversal(self)。"""
    seen: list[PhaseTraversal] = []

    def pred(t: PhaseTraversal) -> bool:
        seen.append(t)
        return True

    traversal = _make_traversal()
    traversal.visit(node_id="perceive.main", max_visits=1, precondition=pred)
    assert seen == [traversal]
