"""D4 cutover: typed predicate evaluator boundary tests.

The old AST-based ``evaluate_restricted_predicate`` has been deleted.
The typed evaluator (:func:`evaluate_predicate`) operates on structured
:class:`Predicate` objects — there is no string parsing, no ``eval``,
no ``ast.parse``, and no attribute path traversal. The only way to
access data is through :class:`PortRef` against declared port names.

These tests verify:
1. The typed evaluator handles all predicate kinds correctly.
2. Port access is restricted to declared ports (no arbitrary attribute access).
3. Unknown fields raise :class:`UnknownFieldError` (fail-loud).
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.errors import UnknownFieldError, UnsetPortError
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.framework.graph.port_reader import PortReader
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.predicate_evaluator import evaluate_predicate


def _reader_with_port(name: str, value: object) -> PortReader:
    reg = PortRegistry()
    reg.set_typed_port(name, value)
    return PortReader(source_node="test", registry=reg)


def test_eq_leaf_matches() -> None:
    reader = _reader_with_port("action", "use_tool")
    pred = Predicate(kind="eq", port=PortRef(name="action"), value="use_tool")
    assert evaluate_predicate(pred, reader=reader) is True


def test_eq_leaf_no_match() -> None:
    reader = _reader_with_port("action", "respond")
    pred = Predicate(kind="eq", port=PortRef(name="action"), value="use_tool")
    assert evaluate_predicate(pred, reader=reader) is False


def test_ne_leaf() -> None:
    reader = _reader_with_port("text", "hello")
    pred = Predicate(kind="ne", port=PortRef(name="text"), value="")
    assert evaluate_predicate(pred, reader=reader) is True


def test_exists_returns_true_when_port_set() -> None:
    reader = _reader_with_port("response", "some text")
    pred = Predicate(kind="exists", port=PortRef(name="response"))
    assert evaluate_predicate(pred, reader=reader) is True


def test_missing_returns_true_when_port_unset() -> None:
    reg = PortRegistry()
    reader = PortReader(source_node="test", registry=reg)
    pred = Predicate(kind="missing", port=PortRef(name="response"))
    assert evaluate_predicate(pred, reader=reader) is True


def test_and_combinator() -> None:
    from pydantic import BaseModel

    class Routing(BaseModel):
        action_type: str
        should_terminate: bool = False

    reg = PortRegistry()
    reg.set_typed_port(
        "routing",
        Routing(action_type="respond", should_terminate=False),
        payload_type=Routing,
    )
    reader = PortReader(source_node="test", registry=reg)
    pred = Predicate(
        kind="and",
        children=(
            Predicate(kind="eq", port=PortRef(name="routing", field="action_type"), value="respond"),
            Predicate(kind="eq", port=PortRef(name="routing", field="should_terminate"), value=False),
        ),
    )
    assert evaluate_predicate(pred, reader=reader) is True


def test_unset_port_raises_for_eq() -> None:
    reg = PortRegistry()
    reader = PortReader(source_node="test", registry=reg)
    pred = Predicate(kind="eq", port=PortRef(name="nonexistent"), value="x")
    with pytest.raises(UnsetPortError):
        evaluate_predicate(pred, reader=reader)


def test_unknown_field_raises() -> None:
    from pydantic import BaseModel

    class Payload(BaseModel):
        action_type: str

    reg = PortRegistry()
    reg.set_typed_port("p", Payload(action_type="x"), payload_type=Payload)
    reader = PortReader(source_node="test", registry=reg)
    pred = Predicate(kind="eq", port=PortRef(name="p", field="nonexistent"), value="x")
    with pytest.raises(UnknownFieldError):
        evaluate_predicate(pred, reader=reader)


def test_not_combinator() -> None:
    reg = PortRegistry()
    reader = PortReader(source_node="test", registry=reg)
    pred = Predicate(
        kind="not",
        children=(Predicate(kind="exists", port=PortRef(name="response")),),
    )
    assert evaluate_predicate(pred, reader=reader) is True
