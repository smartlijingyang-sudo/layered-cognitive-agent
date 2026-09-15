"""Regression test for ``think.budget.check`` wiring into ``think.subgraph``.

Background: PR-3.8.1 (``9e0576472``) added ``think.budget.check`` and an
edge ``think.budget.check → terminal.commit``. ``terminal.commit`` is
declared only in ``bundles/outer/phase_main.yaml`` — it does not exist
as a node in ``think.subgraph``. The Pydantic ``Plan`` validator at
``lca/contracts/protocols/graph/plan.py:118-123`` raised
``ValueError("references unknown node")`` and ``_subgraph_entry_schema``
silently swallowed the lift error (it catches ``PlanLiftError``, which
extends ``ValueError``), so the kernel boot crashed at plan compile with
``PlanLiftError("...: empty inner_io_schema...")`` and
``"...think.budget.check → terminal.commit references unknown node..."``.

This file pins the fix:
  - ``think.budget.check`` declares ``terminal: true`` so
    ``_validate_termination`` is happy.
  - ``think.budget.check → terminal.commit`` edge is dropped (no such
    inner node); natural termination fires when ``should_terminate=true``.
  - The outer ``phase_main.yaml`` gets ``think.main → terminal.commit``
    on ``routing.should_terminate == true`` so the run stops cleanly.

Without this test, the same bug can be reintroduced by anyone wiring a
PR-3.8.x node into ``think_subgraph.yaml`` and re-adding the
``→ terminal.commit`` edge under the false assumption that outer nodes
are reachable from inner plans.
"""

from __future__ import annotations

import yaml
from pydantic import ValidationError

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode


def _load_think_subgraph_plan() -> Plan:
    with open("bundles/think/think_subgraph.yaml", encoding="utf-8") as fh:
        bundle = yaml.safe_load(fh)
    nodes = tuple(
        PlanNode(
            id=n["id"],
            binding=BindingKind.NODE_EXECUTOR,
            entry=(n["id"] == bundle.get("entry", "think.shortcut")),
            terminal=n.get("terminal", False),
        )
        for n in bundle["nodes"]
    )
    edges = tuple(
        PlanEdge(source=e["from"], target=e["to"]) for e in bundle.get("edges", [])
    )
    return Plan(id=bundle["id"], nodes=nodes, edges=edges)


def test_think_subgraph_plan_lifts_clean() -> None:
    """``think.subgraph`` lifts without ``references unknown node``.

    Pre-fix this raised ``ValidationError("references unknown node")``
    for the ``think.budget.check → terminal.commit`` edge and the kernel
    could not boot ``profiles/web-standard.yaml``.
    """
    plan = _load_think_subgraph_plan()
    # Constructor raises ``ValidationError`` on edge target mismatch.
    assert plan.id == "think.subgraph"


def test_think_budget_check_terminates_via_edge_predicate() -> None:
    """``think.budget.check`` terminates by edge-predicate, not by the
    ``terminal: true`` flag.

    Termination is edge-driven per ADR-0217 D4: when the executor
    emits ``should_terminate=true`` the only outgoing edge's
    predicate (``should_terminate=false``) does not match,
    ``select_edge`` returns ``None``, and ``traversal.advance(edge=None)``
    sets ``terminal=True``. Marking the node ``terminal: true`` is
    forbidden by the lifter when an outgoing edge exists ("terminal
    nodes are sinks and their edges never fire"), so the plan uses
    edge-driven termination here. ``think.gate`` (no outgoing edges)
    is the plan's sole ``terminal: true`` node and satisfies
    ``_validate_termination``.
    """
    plan = _load_think_subgraph_plan()
    budget = plan.node("think.budget.check")
    assert budget.terminal is False, (
        "think.budget.check must NOT be marked terminal: true — it "
        "has an outgoing edge to think.context.compact and the "
        "lifter forbids outgoing edges on terminal nodes. "
        "Termination is edge-driven (no edge match → terminate)."
    )
    gate = plan.node("think.gate")
    assert gate.terminal is True, (
        "think.gate must remain terminal: true so _validate_termination "
        "accepts the plan (think.budget.check is no longer terminal)"
    )


def test_think_subgraph_has_no_outer_terminal_commit_edge() -> None:
    """No edge in ``think.subgraph`` may target ``terminal.commit``.

    ``terminal.commit`` is declared in ``bundles/outer/phase_main.yaml``,
    not in the inner think subgraph. An edge to it from the inner plan
    fails the ``Plan._one_entry`` validator because the inner node set
    does not contain ``terminal.commit``.
    """
    plan = _load_think_subgraph_plan()
    cross_subgraph = [e for e in plan.edges if e.target == "terminal.commit"]
    assert cross_subgraph == [], (
        "think.subgraph must not contain edges targeting 'terminal.commit' "
        "(it is an outer node in phase_main.yaml); route should_terminate "
        "out via the typed 'routing' port and let phase_main.yaml's edge "
        "from think.main → terminal.commit catch the signal"
    )


def test_think_budget_check_routing_output_keeps_think_context_compact_path() -> None:
    """Under-cap edge stays wired so the happy path still works.

    Guards against a regression where someone deletes both the
    terminal.commit edge AND the think.context.compact edge while
    "cleaning up" the budget.check wiring.
    """
    plan = _load_think_subgraph_plan()
    compact_edges = [
        e
        for e in plan.edges
        if e.source == "think.budget.check" and e.target == "think.context.compact"
    ]
    assert compact_edges, (
        "the under-cap edge think.budget.check → think.context.compact "
        "must remain so the normal think waterfall still routes through "
        "the context-compaction node"
    )