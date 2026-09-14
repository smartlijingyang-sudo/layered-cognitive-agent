"""Boolean-combinator predicate well-formedness check.

The lifter rejects unknown predicate kinds and missing-port leaf
predicates, but the *shape* of boolean combinator subtrees is
unchecked:

- ``and`` / ``or`` must have at least 2 children (one child is
  redundant — drop the wrapping).
- ``not`` must have exactly 1 child (two children is ambiguous;
  zero is meaningless).
- leaf ``eq`` / ``ne`` must carry a ``value`` to compare against.
- leaf ``in`` ``value`` must be a list / tuple (the runtime
  membership test is meaningless on scalars).
- leaf ``exists`` / ``missing`` must NOT carry a ``value`` (those
  predicates test port presence, not port value).

A malformed subtree like ``not(a, b)`` or ``and(a)`` would not
fail at lift but would explode at runtime in the predicate
evaluator with a confusing ``TypeError`` deep inside the loop.
This check surfaces the structural fault at boot time so the
operator sees it in the same pass that already enumerates
typed-port wiring errors.
"""
from __future__ import annotations

from typing import Any

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan
from lca.contracts.protocols.graph.predicate import Predicate

from .base import PlanCheck


def _check_predicate(pred: Predicate, edge_id: str) -> str | None:
    """Walk one predicate subtree; return the first error string or None."""
    if pred.kind in ("and", "or"):
        if len(pred.children) < 2:
            return (
                f"edge {edge_id}: predicate kind={pred.kind!r} requires >=2 "
                f"children, got {len(pred.children)}"
            )
        for child in pred.children:
            err = _check_predicate(child, edge_id)
            if err is not None:
                return err
        return None
    if pred.kind == "not":
        if len(pred.children) != 1:
            return (
                f"edge {edge_id}: predicate kind='not' requires exactly "
                f"1 child, got {len(pred.children)}"
            )
        return _check_predicate(pred.children[0], edge_id)
    if pred.kind in ("eq", "ne"):
        if getattr(pred, "value", None) is None:
            return (
                f"edge {edge_id}: predicate kind={pred.kind!r} requires a value"
            )
        return None
    if pred.kind == "in":
        value: Any = getattr(pred, "value", None)
        if not isinstance(value, (list, tuple)):
            return (
                f"edge {edge_id}: predicate kind='in' value must be a list, "
                f"got {type(value).__name__}"
            )
        return None
    if pred.kind in ("exists", "missing"):
        if getattr(pred, "value", None) is not None:
            return (
                f"edge {edge_id}: predicate kind={pred.kind!r} should not "
                f"have a value field"
            )
        return None
    # Unknown kind: already rejected at lift time, defensive no-op here.
    return None


class PredicateWellformedCheck(PlanCheck):
    """Reject malformed boolean-combinator predicate subtrees.

    The lifter validates single-edge predicate ports and rejects
    unknown kinds, but does not walk the combinator tree to check
    child arity or leaf payload shape. This check complements
    :class:`TypedPortWiringCheck` and the lifter by surfacing
    ``and(a)`` / ``not(a, b)`` / ``eq``-without-value / etc. at
    boot time, alongside every other plan-level invariant.
    """

    check_id = "predicate_wellformed"
    label = "Boolean combinator predicates are well-formed"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        for edge in plan.edges:
            if not isinstance(edge.when, Predicate):
                # None means "always true" — out of scope.
                continue
            edge_id = f"{edge.source}->{edge.target}"
            err = _check_predicate(edge.when, edge_id)
            if err is not None:
                return PlanLiftError(
                    f"plan {plan_id!r}: {err}",
                    plan_id=plan_id,
                    edge_id=edge_id,
                )
        return None


__all__ = ["PredicateWellformedCheck"]
