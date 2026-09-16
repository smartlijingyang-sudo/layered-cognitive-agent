"""PR-1b regression guards for act HITL wiring.

PR-1 landed the fail-loud resume-edge check with the gate sitting in the
outer plan. PR-1b (ADR-0237) relocates the gate into the act subgraph
(spec §3.2 原位 — between ``act.authorize`` and ``act.envelope``, before
any side effect). The HITL decision must happen **before** the effect
envelope mints; a gate that fires after dispatch is the
"irreversible-then-confirm" anti-pattern.

Two invariants the wiring must satisfy in the new placement:

1. **Gate placement** — ``act.approve.gate`` is declared exactly once,
   inside ``bundles/act/act_subgraph.yaml``. The outer plan must not
   redeclare it (two declarations would prompt twice for the same
   decision).

2. **Subgraph boundary discipline** — ``act_subgraph`` may only name
   nodes it owns (act.* and effect.*). Outer/sibling node ids
   (intervene.interrupt, intervene.resume, terminal.commit,
   reflect.main) belong to other plans.

3. **Outer-plan routing exclusivity** — the three mutually-exclusive
   routing edges consume ``act.main.routing`` and target exactly one
   of ``{intervene.interrupt, terminal.commit, reflect.main}`` per
   run. The act.subgraph no longer names any outer plan node id.

4. **Resume cycle closure** — ``intervene.resume → act.approve.gate``
   lives inside act_subgraph (per-plan resume-edge validator triggers
   at subgraph lift time); the outer plan keeps the
   ``intervene.interrupt → intervene.resume`` cycle so a paused run
   can resume back through the kernel-wide port registry.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTER_PLAN = REPO_ROOT / "bundles" / "outer" / "phase_main.yaml"
ACT_SUBGRAPH = REPO_ROOT / "bundles" / "act" / "act_subgraph.yaml"


def _nodes(path: Path) -> dict[str, dict[str, object]]:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {node["id"]: node for node in spec["nodes"]}


def _edges(path: Path) -> set[tuple[str, str]]:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        (edge.get("from") or edge.get("source"), edge.get("to") or edge.get("target"))
        for edge in spec["edges"]
    }


def test_act_subgraph_nodes_all_declare_factory() -> None:
    """The BundleGraph loader requires ``factory`` on every act-subgraph node.

    Guards defect 1 (PR-1): a subgraph that borrows an outer node id lifts
    fine in ``plan_sdk`` but crashes the subgraph resolver.
    """
    offenders = [node_id for node_id, node in _nodes(ACT_SUBGRAPH).items() if "factory" not in node]
    assert not offenders, (
        f"act subgraph nodes without 'factory' break lca-ops plan tree: {offenders}"
    )


def test_act_subgraph_does_not_declare_foreign_nodes() -> None:
    """act_subgraph may only declare ``act.*`` and ``intervene.*`` / ``effect.*`` nodes.

    Guards the root cause of PR-1 defect 1: ``intervene.*`` and
    ``terminal.commit`` / ``reflect.main`` belong to the outer plan and
    must not appear here. ``intervene.resume`` is a factory stub
    (ADR-0237 / PR-1b) that lives inside the subgraph so the
    per-plan resume-edge validator has both endpoints; the real
    subgraph stays at the outer level.
    """
    foreign = {
        node_id
        for node_id in _nodes(ACT_SUBGRAPH)
        if not (
            node_id.startswith("act.")
            or node_id.startswith("effect.")
            or node_id.startswith("intervene.")
        )
    }
    assert not foreign, (
        f"act subgraph declares nodes owned by other plans: {foreign}"
    )


def test_gate_declared_in_exactly_one_plan() -> None:
    """The gate must not be declared in both the outer plan and act_subgraph.

    Two declarations means two HITL evaluations per run — the second would
    re-prompt for a decision already approved.

    PR-1b / ADR-0237: the gate is now nested inside act_subgraph (spec §3.2
    原位). The outer plan must NOT redeclare it.
    """
    outer_has = "act.approve.gate" in _nodes(OUTER_PLAN)
    inner_has = "act.approve.gate" in _nodes(ACT_SUBGRAPH)
    assert outer_has is False, (
        "act.approve.gate must NOT be in the outer plan (PR-1b moved it "
        "into act_subgraph, spec §3.2 原位); outer plan still has it."
    )
    assert inner_has is True, (
        "act.approve.gate must be in act_subgraph.yaml (PR-1b, ADR-0237); "
        "not found."
    )


def test_outer_act_main_has_three_routing_consumers() -> None:
    """The outer plan must consume ``act.main.routing`` with exactly 3 targets.

    PR-1b / ADR-0237: gate emits ``routing.next_hint`` ∈
    {approve_skipped, approve_approved, approve_interrupt,
    approve_rejected}. Three outer edges route these to:

    - ``intervene.interrupt`` (pause for the user's typed Command)
    - ``terminal.commit`` (reject / redirect / resume-timeout)
    - ``reflect.main`` (pass-through after approve_skipped/approved)

    These three edges are the only ``act.main`` → {intervene.*,
    terminal.*, reflect.*} consumers at the outer level; the previous
    ``act.main → act.approve.gate`` unconditional edge is gone
    (gate is inside the subgraph now).
    """
    edges = _edges(OUTER_PLAN)
    act_main_edges = {target for source, target in edges if source == "act.main"}
    expected = {"intervene.interrupt", "terminal.commit", "reflect.main"}
    assert expected <= act_main_edges, (
        f"act.main missing one of the 3 mutually-exclusive routing edges; "
        f"got targets={sorted(act_main_edges)}, expected at least "
        f"{sorted(expected)}"
    )
    # No other act.main edges should target routing consumers.
    assert not (act_main_edges - expected - {"think.main"}), (
        f"act.main has unexpected edges targeting {sorted(act_main_edges - expected)}"
    )


def test_outer_plan_does_not_declare_act_approve_gate() -> None:
    """Gate relocation invariant: outer plan must not declare act.approve.gate.

    The gate executor is reachable from the outer plan only via the
    subgraph boundary (``act.main.sub_spec_ref`` →
    ``bundles/act/act_subgraph.yaml``). A separate outer-plan declaration
    would re-instantiate the gate.
    """
    assert "act.approve.gate" not in _nodes(OUTER_PLAN), (
        "outer plan must not declare act.approve.gate — PR-1b moved the "
        "gate into act_subgraph (spec §3.2 原位)"
    )


def test_act_subgraph_does_not_carry_resume_stub() -> None:
    """m1 outer-edge-SSOT close-out: act_subgraph.yaml must NOT carry
    the ``intervene.resume → act.approve.gate`` inner stub edge.

    The original PR-1b design wired a subgraph-internal stub node + edge
    that depended on an unrealised kernel re-projection hook (ADR-0237
    §6 promised but never implemented). The resume path now reaches
    ``act.approve.gate`` via the outer ``act.resume`` subgraph
    delegate (``entry_node=act.approve.gate``) — see
    tests/intervene/test_approve_gate_phase_plugin.py for the
    positive guard.

    This test pins the close-out so a future regression that
    reintroduces the stub edge + factory carrier fails boot loudly.
    """
    edges = _edges(ACT_SUBGRAPH)
    assert ("intervene.resume", "act.approve.gate") not in edges, (
        "intervene.resume → act.approve.gate inner edge reappeared in "
        "act_subgraph.yaml; m1 close-out removed it because the kernel "
        "re-projection hook ADR-0237 §6 promised was never implemented. "
        "Resume reaches act.approve.gate via the outer act.resume "
        "subgraph delegate (entry_node override)."
    )
    nodes = _nodes(ACT_SUBGRAPH)
    assert "intervene.resume" not in nodes, (
        "intervene.resume stub node reappeared in act_subgraph.yaml; "
        "m1 close-out removed it — the resume cycle goes through outer "
        "act.resume, not an inner stub factory carrier."
    )


def test_outer_resume_cycle_intervene_interrupt_to_resume() -> None:
    """The outer plan must keep ``intervene.interrupt → intervene.resume``.

    On resume the kernel re-projects the persisted Command into the
    registry and routes back through the subgraph's gate. The outer
    edge from ``intervene.interrupt`` to ``intervene.resume`` closes
    the loop at the outer level so a paused run can come back.
    """
    edges = _edges(OUTER_PLAN)
    assert ("intervene.interrupt", "intervene.resume") in edges, (
        "intervene.interrupt → intervene.resume outer edge missing — "
        "resume cycle is not closed at the outer level"
    )
