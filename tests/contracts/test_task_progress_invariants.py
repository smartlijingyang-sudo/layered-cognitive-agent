"""TaskProgress dataclass invariants (ADR-0214 §3.1 / §3.6).

- confidence 越界 → :class:`ContractViolation`
- frozen/slots 不变
- ``is_terminal()`` 边界判定
"""

from __future__ import annotations

import dataclasses

import pytest

from lca.contracts.errors import ContractViolation
from lca.contracts.models.core.execution.task_progress import TaskProgress


def test_default_construction_is_empty_quadruple() -> None:
    """默认构造:四元组全空,confidence 0.0,无 termination_reason。"""
    tp = TaskProgress()
    assert tp.completed == ()
    assert tp.remaining == ()
    assert tp.confidence == 0.0
    assert tp.termination_reason is None
    # is_terminal 默认 False(remaining 非空)
    assert tp.is_terminal() is False


def test_confidence_above_one_raises_contract_violation() -> None:
    """confidence > 1.0 必须 fail-loud (C13 fail-loud)。"""
    with pytest.raises(ContractViolation):
        TaskProgress(confidence=1.01)


def test_confidence_below_zero_raises_contract_violation() -> None:
    """confidence < 0.0 必须 fail-loud。"""
    with pytest.raises(ContractViolation):
        TaskProgress(confidence=-0.01)


def test_confidence_at_boundaries_is_valid() -> None:
    """confidence = 0.0 与 1.0 是边界合法值(闭区间)。"""
    a = TaskProgress(confidence=0.0)
    b = TaskProgress(confidence=1.0)
    assert a.confidence == 0.0
    assert b.confidence == 1.0


def test_confidence_non_numeric_raises_contract_violation() -> None:
    """非数值 confidence 必须 fail-loud(防 bool/int 误传)。"""
    with pytest.raises(ContractViolation):
        TaskProgress(confidence=True)
    with pytest.raises(ContractViolation):
        TaskProgress(confidence="0.5")  # type: ignore[arg-type]


def test_completed_must_be_tuple() -> None:
    """completed 不是 tuple → fail-loud(防止 fold 中 set/list 渗漏)。"""
    with pytest.raises(ContractViolation):
        TaskProgress(completed=["a"])  # type: ignore[arg-type]


def test_remaining_must_be_tuple() -> None:
    """remaining 不是 tuple → fail-loud。"""
    with pytest.raises(ContractViolation):
        TaskProgress(remaining=["x"])  # type: ignore[arg-type]


def test_frozen_no_mutation() -> None:
    """frozen=True → 字段不可 mutate。"""
    tp = TaskProgress(completed=("a",), remaining=("b",), confidence=0.5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        tp.confidence = 0.9  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        tp.completed = ("z",)  # type: ignore[misc]


def test_slots_prevent_extra_attributes() -> None:
    """slots=True → 设置 dataclass 未声明的字段抛 AttributeError 或 TypeError。

    注:CPython 对 ``__slots__`` 实例赋值未声明字段抛 :class:`TypeError`
    ("__slots__ does not define 'invented'"),而非 :class:`AttributeError`;
    测试接受两者作为"设置被拒绝"的标志(C4 静态不可变)。
    """
    tp = TaskProgress()
    with pytest.raises((AttributeError, TypeError)):
        tp.invented = "nope"  # type: ignore[attr-defined]


def test_is_terminal_true_when_remaining_empty_and_confidence_high() -> None:
    """is_terminal():remaining=[] + confidence≥0.8 → True。"""
    tp = TaskProgress(completed=("a", "b"), remaining=(), confidence=0.8)
    assert tp.is_terminal() is True


def test_is_terminal_false_when_confidence_just_below_threshold() -> None:
    """is_terminal():confidence=0.79(< 0.8) → False。"""
    tp = TaskProgress(completed=("a",), remaining=(), confidence=0.79)
    assert tp.is_terminal() is False


def test_is_terminal_false_when_remaining_non_empty() -> None:
    """is_terminal():remaining 非空 → False(即使 confidence=1.0)。"""
    tp = TaskProgress(completed=("a",), remaining=("b",), confidence=1.0)
    assert tp.is_terminal() is False


def test_equality_and_hash() -> None:
    """同四元组 == 且 hash 一致(便于 fold 用作 dict key)。"""
    a = TaskProgress(completed=("x",), remaining=("y",), confidence=0.5)
    b = TaskProgress(completed=("x",), remaining=("y",), confidence=0.5)
    c = TaskProgress(completed=("x",), remaining=("y",), confidence=0.6)
    assert a == b
    assert hash(a) == hash(b)
    assert a != c


def test_as_dict_roundtrip() -> None:
    """as_dict:可读视图(诊断用)。"""
    tp = TaskProgress(
        completed=("a",),
        remaining=("b", "c"),
        confidence=0.42,
        termination_reason="max_steps",
    )
    assert tp.as_dict() == {
        "completed": ["a"],
        "remaining": ["b", "c"],
        "confidence": 0.42,
        "termination_reason": "max_steps",
    }
