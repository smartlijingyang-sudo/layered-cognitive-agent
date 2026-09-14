"""Tests for evaluate_predicate — pure structured predicate solver.

Task 3 of the typed port graph redesign: evaluate_predicate walks a
Predicate tree and resolves it against a PortReader. No AST, no string
parsing, no silent None.

TDD RED: these tests must fail before the implementation lands.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.framework.graph.port_reader import PortReader
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.predicate_evaluator import evaluate_predicate


class _DecisionPayload(BaseModel):
    action_type: str = "respond"
    should_terminate: bool = False
    tags: list[str] = []


def _make_reader(**ports: object) -> PortReader:
    """Helper: build a PortReader with set_typed_port for BaseModel values."""
    reg = PortRegistry()
    for name, value in ports.items():
        ptype = type(value) if isinstance(value, BaseModel) else None
        reg.set_typed_port(name, value, payload_type=ptype)  # type: ignore[arg-type]
    return PortReader(source_node="test_node", registry=reg)


def test_leaf_kinds_eq_ne_in() -> None:
    """eq/ne/in compare port values (or fields) to constants."""
    decision = _DecisionPayload(action_type="use_tool", should_terminate=False)
    reader = _make_reader(decision=decision)

    # eq on a field
    assert (
        evaluate_predicate(
            Predicate(
                kind="eq", port=PortRef(name="decision", field="action_type"), value="use_tool"
            ),
            reader=reader,
        )
        is True
    )
    # ne on a field
    assert (
        evaluate_predicate(
            Predicate(kind="ne", port=PortRef(name="decision", field="action_type"), value="stop"),
            reader=reader,
        )
        is True
    )
    # in on a field
    assert (
        evaluate_predicate(
            Predicate(
                kind="in",
                port=PortRef(name="decision", field="action_type"),
                value=["use_tool", "stop"],
            ),
            reader=reader,
        )
        is True
    )
    # negative: eq that doesn't match
    assert (
        evaluate_predicate(
            Predicate(kind="eq", port=PortRef(name="decision", field="action_type"), value="stop"),
            reader=reader,
        )
        is False
    )


def test_exists_and_missing_kinds() -> None:
    """exists/missing check port presence, not value truthiness."""
    decision = _DecisionPayload()
    reader = _make_reader(decision=decision)

    # exists: port is set → True
    assert evaluate_predicate(Predicate(kind="exists", port=PortRef(name="decision")), reader=reader) is True
    # missing: port is set → False
    assert evaluate_predicate(Predicate(kind="missing", port=PortRef(name="decision")), reader=reader) is False
    # exists on unset port → False (use a valid PortName that was never written)
    assert evaluate_predicate(Predicate(kind="exists", port=PortRef(name="observation")), reader=reader) is False
    # missing on unset port → True
    assert evaluate_predicate(Predicate(kind="missing", port=PortRef(name="observation")), reader=reader) is True


def test_boolean_and_or_not() -> None:
    """and/or/not combine child predicates recursively."""
    decision = _DecisionPayload(action_type="use_tool", should_terminate=False)
    reader = _make_reader(decision=decision)

    # and: both must be true
    assert (
        evaluate_predicate(
            Predicate(
                kind="and",
                children=(
                    Predicate(
                        kind="eq",
                        port=PortRef(name="decision", field="action_type"),
                        value="use_tool",
                    ),
                    Predicate(
                        kind="eq",
                        port=PortRef(name="decision", field="should_terminate"),
                        value=False,
                    ),
                ),
            ),
            reader=reader,
        )
        is True
    )

    # and: one false → False
    assert (
        evaluate_predicate(
            Predicate(
                kind="and",
                children=(
                    Predicate(
                        kind="eq",
                        port=PortRef(name="decision", field="action_type"),
                        value="use_tool",
                    ),
                    Predicate(
                        kind="eq",
                        port=PortRef(name="decision", field="should_terminate"),
                        value=True,
                    ),
                ),
            ),
            reader=reader,
        )
        is False
    )

    # or: one true → True
    assert (
        evaluate_predicate(
            Predicate(
                kind="or",
                children=(
                    Predicate(
                        kind="eq", port=PortRef(name="decision", field="action_type"), value="stop"
                    ),
                    Predicate(
                        kind="eq",
                        port=PortRef(name="decision", field="action_type"),
                        value="use_tool",
                    ),
                ),
            ),
            reader=reader,
        )
        is True
    )

    # not: negates child
    assert (
        evaluate_predicate(
            Predicate(
                kind="not",
                children=(
                    Predicate(
                        kind="eq",
                        port=PortRef(name="decision", field="should_terminate"),
                        value=True,
                    ),
                ),
            ),
            reader=reader,
        )
        is True
    )


def test_leaf_kinds_require_port_field() -> None:
    """All leaf kinds (eq/ne/in/exists/missing) require the port field on Predicate."""
    decision = _DecisionPayload()
    reader = _make_reader(decision=decision)

    # Leaf without port → ValueError
    for kind in ("eq", "ne", "in", "exists", "missing"):
        with pytest.raises(ValueError, match="port"):
            evaluate_predicate(Predicate(kind=kind, port=None, value="whatever"), reader=reader)


def test_exists_missing_with_field_ref() -> None:
    """exists/missing can also target a specific field on a port's payload."""
    decision = _DecisionPayload(action_type="respond")
    reader = _make_reader(decision=decision)

    # Field exists on the payload → True
    assert (
        evaluate_predicate(
            Predicate(kind="exists", port=PortRef(name="decision", field="action_type")),
            reader=reader,
        )
        is True
    )
