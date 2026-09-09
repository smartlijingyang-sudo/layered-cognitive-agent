"""ADR-0214 §6 PR-C: ``PhaseNode`` 三件套 schema 字段契约。

锁定 ``precondition`` / ``terminal_predicate`` 字段默认值、显式赋值与
空字符串拒绝语义。任何在 harness / compiler / 测试中构造 ``PhaseNode``
的代码都依赖此契约,改动必须同时改此文件。
"""

from __future__ import annotations

import dataclasses

import pytest

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    PhaseNode,
)


def _make_minimal_node(**overrides: object) -> PhaseNode:
    """Build the smallest valid PhaseNode and apply test overrides."""
    base: dict[str, object] = {
        "id": "n",
        "semantic_phase": SemanticPhase.PERCEIVE,
        "binding": "phase.perceive.standard",
        "max_visits": 1,
    }
    base.update(overrides)
    return PhaseNode(**base)  # type: ignore[arg-type]


def test_phase_node_accepts_explicit_precondition_string() -> None:
    """``precondition`` 显式赋值为非空字符串不抛,字段值透传。"""
    node = _make_minimal_node(precondition="perceive.has_minimum_context")
    assert node.precondition == "perceive.has_minimum_context"


def test_phase_node_default_precondition_is_none() -> None:
    """``precondition`` 默认 None,等价于历史行为(无入口校验)。"""
    node = _make_minimal_node()
    assert node.precondition is None


def test_phase_node_default_terminal_predicate_is_none() -> None:
    """``terminal_predicate`` 默认 None,等价于历史行为(无出口谓词)。"""
    node = _make_minimal_node()
    assert node.terminal_predicate is None


def test_phase_node_accepts_explicit_terminal_predicate_string() -> None:
    """``terminal_predicate`` 显式赋值为非空字符串不抛,字段值透传。"""
    node = _make_minimal_node(terminal_predicate="perceive.context_complete")
    assert node.terminal_predicate == "perceive.context_complete"


def test_phase_node_rejects_empty_precondition_string() -> None:
    """``precondition`` 显式赋值空字符串 → PG-007 失败(必须非空或 None)。"""
    with pytest.raises(DeclarativeValidationError) as exc_info:
        _make_minimal_node(precondition="")
    assert exc_info.value.code == "PG-007"


def test_phase_node_rejects_whitespace_precondition_string() -> None:
    """``precondition`` 显式赋值纯空白字符串 → PG-007 失败。"""
    with pytest.raises(DeclarativeValidationError) as exc_info:
        _make_minimal_node(precondition="   ")
    assert exc_info.value.code == "PG-007"


def test_phase_node_rejects_empty_terminal_predicate_string() -> None:
    """``terminal_predicate`` 显式赋值空字符串 → PG-007 失败。"""
    with pytest.raises(DeclarativeValidationError) as exc_info:
        _make_minimal_node(terminal_predicate="")
    assert exc_info.value.code == "PG-007"


def test_phase_node_is_frozen() -> None:
    """``PhaseNode`` frozen=True: 字段不可变(保护契约)。"""
    node = _make_minimal_node(precondition="x")
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        node.precondition = "y"  # type: ignore[misc]
