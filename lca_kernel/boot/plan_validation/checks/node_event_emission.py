"""Node observability-event emission check.

Reject plans whose entry / terminal nodes do not declare the
events that downstream debug tooling relies on as anchors.

Why this matters
----------------

Industry graph runtimes (Airflow / Temporal / Prefect / React Flow /
igraph) all anchor debug traces on ``start`` / ``end`` / ``fail`` /
``skip`` events that each node emits on entry and exit. Without
these anchors, a journal trace for a node with
``emit_on_enter: []`` and ``emit_on_exit: []`` is a black box —
the trace records nothing at the node boundary and runtime errors
inside the node have no static place to attach to.

The v2 graph framework already exposes ``emit_on_enter`` /
``emit_on_exit`` lists on each node's ``config`` mapping, but does
not *require* non-leaf nodes to populate them. This check fills
that gap at boot so the operator sees the failure next to the plan
definition, instead of debugging a missing trace frame at runtime.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class NodeEventEmissionCheck(PlanCheck):
    """Entry / terminal nodes must declare observability events.

    Three rules apply:

    1. Entry nodes must declare at least one ``emit_on_enter``
       event — the journal needs a ``plan.start`` anchor so the
       trace has a definite beginning.
    2. Terminal nodes must declare at least one ``emit_on_exit``
       event — the journal needs a ``plan.end`` anchor so the
       trace has a definite completion signal.
    3. Either event list that is present must be a list/tuple
       (not a bare string, int, or other scalar) — fail loud on
       a malformed type so the operator catches the typo at boot
       rather than at runtime.

    Subgraph delegate nodes are exempt: their inner plan owns the
    observability contract, and the outer wrapper just routes the
    call. Plain non-leaf nodes without entry / terminal flags are
    also exempt from the *required* rule — they may still declare
    events for granular traces, but the absence is not an error.
    """

    check_id = "node_event_emission"
    label = "Node emits observability events on enter/exit"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        for node in plan.nodes:
            if node.subgraph_ref is not None:
                continue

            enter = _read_emits(node, "emit_on_enter")
            exit_ = _read_emits(node, "emit_on_exit")

            # Malformed types fail loud regardless of entry/terminal flag.
            if enter is not None and enter[0] == "malformed":
                return PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} "
                    f"emit_on_enter malformed: {enter[1]!r}; "
                    f"expected a list of event names so debug "
                    f"traces have a typed anchor.",
                    plan_id=plan_id,
                    node_id=node.id,
                )
            if exit_ is not None and exit_[0] == "malformed":
                return PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} "
                    f"emit_on_exit malformed: {exit_[1]!r}; "
                    f"expected a list of event names so debug "
                    f"traces have a typed anchor.",
                    plan_id=plan_id,
                    node_id=node.id,
                )

            # Entry rule: must declare ≥ 1 enter event.
            if node.entry and _is_empty_or_absent(enter):
                return PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} "
                    f"entry needs emit_on_enter with at least one "
                    f"event (e.g. 'plan.start'); every entry node "
                    f"must declare observability events so debug "
                    f"traces have anchors.",
                    plan_id=plan_id,
                    node_id=node.id,
                )

            # Terminal rule: must declare ≥ 1 exit event.
            if node.terminal and _is_empty_or_absent(exit_):
                return PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} "
                    f"terminal needs emit_on_exit with at least one "
                    f"event (e.g. 'plan.end'); every terminal node "
                    f"must declare observability events so debug "
                    f"traces have anchors.",
                    plan_id=plan_id,
                    node_id=node.id,
                )
        return None


def _read_emits(node: object, key: str) -> tuple[str, object] | None:
    """Read an emit-list field from a node's ``config`` mapping.

    Returns a tagged tuple so the caller can distinguish the three
    relevant shapes without re-running isinstance checks:

    - ``None`` when the key is absent (not declared — neutral).
    - ``("malformed", value)`` when the key is present but not a
      list/tuple.
    - ``("declared", list)`` when the key is present and well-typed
      (the value is copied into a list so callers can mutate / measure).
    """
    config = getattr(node, "config", None)
    if not isinstance(config, dict):
        return None
    val = config.get(key)
    if val is None:
        return None
    if not isinstance(val, (list, tuple)):
        return ("malformed", val)
    return ("declared", list(val))


def _is_empty_or_absent(read: tuple[str, object] | None) -> bool:
    """True when the emit field is absent or declared as an empty list."""
    if read is None:
        return True
    if read[0] == "declared":
        return len(read[1]) == 0
    # "malformed" is handled separately; do not treat it as "empty".
    return False


__all__ = ["NodeEventEmissionCheck"]
