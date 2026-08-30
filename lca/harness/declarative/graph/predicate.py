"""Side-effect-free predicate evaluation for declarative phase graphs."""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable, Mapping
from typing import cast

from lca.contracts.protocols.declarative.declarative_phase_graph import (
    DeclarativeValidationError,
    PhaseResult,
)


def evaluate_restricted_predicate(
    expression: str, *, result: PhaseResult, artifacts: Mapping[str, object]
) -> bool:
    """Evaluate the declarative edge DSL with a fixed, side-effect-free grammar."""
    normalized = expression.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise DeclarativeValidationError(
            "PS-001", f"invalid restricted predicate: {expression!r}"
        ) from exc
    roots = {
        "result": result,
        "artifact": artifacts.get("payload"),
        "observation": artifacts.get("observation"),
        "budget": artifacts.get("budget"),
    }
    return bool(_evaluate_ast(tree.body, roots))


def _evaluate_ast(node: ast.AST, roots: Mapping[str, object]) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in roots:
            raise DeclarativeValidationError("PS-001", f"predicate root is not allowed: {node.id}")
        return roots[node.id]
    if isinstance(node, ast.Attribute):
        return _read_member(_evaluate_ast(node.value, roots), node.attr)
    if isinstance(node, ast.Subscript):
        target = _evaluate_ast(node.value, roots)
        index = _evaluate_ast(node.slice, roots)
        if isinstance(target, Mapping):
            return cast("Mapping[object, object]", target)[index]
        if isinstance(target, (list, tuple)) and isinstance(index, int):
            return target[index]
        raise DeclarativeValidationError("PS-001", "predicate subscript target is not indexable")
    if isinstance(node, ast.BoolOp):
        values = [_evaluate_ast(item, roots) for item in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _evaluate_ast(node.operand, roots)
    if isinstance(node, ast.Compare):
        left = _evaluate_ast(node.left, roots)
        for comparison, comparator in zip(node.ops, node.comparators, strict=True):
            right = _evaluate_ast(comparator, roots)
            if isinstance(comparison, ast.Eq):
                matches = left == right
            elif isinstance(comparison, ast.NotEq):
                matches = left != right
            elif isinstance(comparison, ast.In):
                matches = _contains(right, left)
            elif isinstance(comparison, ast.NotIn):
                matches = not _contains(right, left)
            elif isinstance(comparison, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                matches = _ordered_compare(left, right, comparison)
            else:
                raise DeclarativeValidationError("PS-001", "unsupported predicate comparison")
            if not matches:
                return False
            left = right
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return tuple(_evaluate_ast(item, roots) for item in node.elts)
    raise DeclarativeValidationError("PS-001", "predicate uses forbidden syntax")


def _contains(container: object, item: object) -> bool:
    """Evaluate membership only for explicitly supported predicate containers."""
    if isinstance(container, (str, bytes, tuple, list, set, frozenset, Mapping)):
        return item in container
    raise DeclarativeValidationError("PS-001", "predicate membership target is not supported")


def _ordered_compare(left: object, right: object, comparison: ast.cmpop) -> bool:
    """Perform an ordered comparison without widening the evaluator to Any."""
    try:
        if isinstance(comparison, ast.Lt):
            return cast("Callable[[object, object], bool]", operator.lt)(left, right)
        if isinstance(comparison, ast.LtE):
            return cast("Callable[[object, object], bool]", operator.le)(left, right)
        if isinstance(comparison, ast.Gt):
            return cast("Callable[[object, object], bool]", operator.gt)(left, right)
        if isinstance(comparison, ast.GtE):
            return cast("Callable[[object, object], bool]", operator.ge)(left, right)
    except TypeError as exc:
        raise DeclarativeValidationError("PS-001", "predicate operands are not orderable") from exc
    raise DeclarativeValidationError("PS-001", "unsupported predicate comparison")


def _read_member(value: object, key: str) -> object:
    if key.startswith("_"):  # Prevent private reflection and arbitrary call paths.
        raise DeclarativeValidationError("PS-001", "predicate may not access private attributes")
    if isinstance(value, Mapping):
        return value.get(key)
    return cast("object", getattr(value, key))


__all__ = ["evaluate_restricted_predicate"]
