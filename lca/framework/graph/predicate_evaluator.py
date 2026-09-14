"""evaluate_predicate — pure structured predicate solver.

Walks a :class:`Predicate` tree and resolves it against a
:class:`PortReader`. No AST, no string parsing, no silent ``None``.

Leaf kinds (``eq``, ``ne``, ``in``, ``exists``, ``missing``) require
``Predicate.port`` to be set; a missing port raises :class:`ValueError`.
Boolean kinds (``and``, ``or``, ``not``) recursively dispatch to children.

The evaluator is a pure function of the predicate and the reader —
no side effects, no mutation, no environment access.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.errors import UnknownFieldError, UnsetPortError
from lca.contracts.protocols.graph.predicate import Predicate
from lca.framework.graph.port_reader import PortReader

_LEAF_KINDS = frozenset({"eq", "ne", "in", "exists", "missing"})
_BOOL_KINDS = frozenset({"and", "or", "not"})


def evaluate_predicate(pred: Predicate, *, reader: PortReader) -> bool:
    """Evaluate ``pred`` against ``reader``; return True or False.

    Pure function — no state, no mutation.
    Raises :class:`ValueError` if a leaf predicate has no ``port``.
    Raises :class:`UnsetPortError` / :class:`UnknownFieldError`
    transparently from the reader when a port or field is missing
    (except for ``exists`` / ``missing`` which handle absence gracefully).
    """
    kind = pred.kind

    if kind in _LEAF_KINDS:
        return _eval_leaf(pred, reader)
    if kind in _BOOL_KINDS:
        return _eval_bool(pred, reader)
    raise ValueError(f"unknown predicate kind: {kind!r}")


def _eval_leaf(pred: Predicate, reader: PortReader) -> bool:
    """Evaluate a leaf predicate (eq/ne/in/exists/missing)."""
    if pred.port is None:
        raise ValueError(
            f"leaf predicate kind={pred.kind!r} requires 'port' field, got None"
        )

    kind = pred.kind

    # exists/missing handle port absence gracefully (no raise).
    if kind == "exists":
        if pred.port.field is not None:
            return _field_exists(pred, reader)
        return reader.port_has_value(pred.port.name)

    if kind == "missing":
        if pred.port.field is not None:
            return not _field_exists(pred, reader)
        return not reader.port_has_value(pred.port.name)

    # eq/ne/in require the port to be set — let UnsetPortError propagate.
    value = reader.read(pred.port)

    if kind == "eq":
        return value == pred.value
    if kind == "ne":
        return value != pred.value
    if kind == "in":
        return value in pred.value

    raise ValueError(f"unhandled leaf kind: {kind!r}")  # pragma: no cover


def _field_exists(pred: Predicate, reader: PortReader) -> bool:
    """Check whether a specific field exists on a port's payload."""
    if pred.port is None:
        return False
    if not reader.port_has_value(pred.port.name):
        return False
    try:
        reader.read(pred.port)
    except (UnsetPortError, UnknownFieldError, KeyError):
        return False
    return True


def _eval_bool(pred: Predicate, reader: PortReader) -> bool:
    """Evaluate a boolean combinator (and/or/not)."""
    kind = pred.kind

    if kind == "and":
        return all(evaluate_predicate(child, reader=reader) for child in pred.children)
    if kind == "or":
        return any(evaluate_predicate(child, reader=reader) for child in pred.children)
    if kind == "not":
        if len(pred.children) != 1:
            raise ValueError(
                f"'not' predicate requires exactly 1 child, got {len(pred.children)}"
            )
        return not evaluate_predicate(pred.children[0], reader=reader)

    raise ValueError(f"unhandled bool kind: {kind!r}")  # pragma: no cover


__all__ = ["evaluate_predicate"]
