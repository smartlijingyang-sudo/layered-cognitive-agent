"""PR-1 acceptance — boot fail-loud when act.approve.gate lacks resume edge.

HITL without a resume edge is unsafe: an interrupt can pause a run
but never recover. PR-1 makes this fail-loud at boot: any plan that
declares ``act.approve.gate`` must also declare a cross-subgraph
``intervene.resume → act.approve.gate`` edge. The check is per-plan
(both the outer plan and the inner act_subgraph plan that hosts the
gate's executor must satisfy it).
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from lca.framework.graph.lifter import lift_graph_spec


def _apply_entry_fallback(mapping):
    """Mirror ``_apply_entry_fallback`` from ``lca_kernel.boot.plan_validation``.

    Mark the first node as :class:`Plan.entry` if no node carries
    ``entry: True`` — same shape the production validator uses.
    """
    spec = dict(mapping)
    nodes = list(spec.get("nodes") or ())
    if nodes and not any(
        isinstance(n, dict) and n.get("entry") for n in nodes
    ):
        nodes[0] = {**nodes[0], "entry": True}
        spec["nodes"] = nodes
    return spec


def test_missing_approval_resume_node_raises_planlifterror(tmp_path: Path) -> None:
    """profile 含 act.approve.gate 但缺 intervene.resume → act.approve.gate 边 → PlanLiftError。"""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        dedent(
            """\
            id: bad.subgraph
            region: act
            nodes:
              - id: act.authorize
                factory: act.authorize
                inputs: [decision]
                outputs: [decision, approval_required]
              - id: act.envelope
                factory: act.envelope
                inputs: [decision]
                outputs: [envelope]
              - id: act.approve.gate
                factory: act.approve.gate
                inputs: [decision]
                outputs: [decision, routing]
              - id: terminal.commit
                binding: terminate
                terminal: true
                inputs: [decision]
                outputs: [terminal_outcome]
            edges:
              - {from: act.authorize, to: act.approve.gate, when: true}
              - {from: act.approve.gate, to: act.envelope, when: true}
              # 故意缺 intervene.resume → act.approve.gate 跨子图 resume 边
            """
        ),
        encoding="utf-8",
    )

    raw = __import__("yaml").safe_load(bad_yaml.read_text(encoding="utf-8"))
    spec = _apply_entry_fallback(raw)

    with pytest.raises(Exception) as exc:
        lift_graph_spec(spec)
    # We assert on a substring so the test is robust to the exact
    # error message wording. The lifter uses PlanLiftError for typed
    # plan failures; we accept any subclass that mentions the gate.
    message = str(exc.value)
    assert "act.approve.gate" in message, (
        "lifter must reference act.approve.gate in the failure message "
        "(node_id=act.approve.gate is the SSOT for the fail-loud "
        "diagnostic); got: " + message
    )
    assert "resume" in message.lower(), (
        "lifter must explain why the resume edge is required; got: "
        + message
    )


def test_approval_resume_node_edge_present_passes_lift(tmp_path: Path) -> None:
    """Negative control: plan WITH the resume edge lifts cleanly."""
    good_yaml = tmp_path / "good.yaml"
    good_yaml.write_text(
        dedent(
            """\
            id: good.subgraph
            region: act
            approval_resume_node: act.approve.gate
            nodes:
              - id: act.authorize
                factory: act.authorize
                inputs: [decision]
                outputs: [decision, approval_required]
              - id: act.envelope
                factory: act.envelope
                inputs: [decision]
                outputs: [envelope]
              - id: act.approve.gate
                factory: act.approve.gate
                inputs: [decision]
                outputs: [decision, routing]
              - id: intervene.resume
                factory: intervene.resume
                inputs: [command]
                outputs: [decision]
              - id: terminal.commit
                binding: terminate
                terminal: true
                inputs: [decision]
                outputs: [terminal_outcome]
            edges:
              - {from: act.authorize, to: act.approve.gate, when: true}
              - {from: act.approve.gate, to: act.envelope, when: true}
              - {from: intervene.resume, to: act.approve.gate, when: true}
            """
        ),
        encoding="utf-8",
    )

    raw = __import__("yaml").safe_load(good_yaml.read_text(encoding="utf-8"))
    spec = _apply_entry_fallback(raw)
    plan = lift_graph_spec(spec)
    assert any(n.id == "act.approve.gate" for n in plan.nodes)
    assert any(
        e.source == "intervene.resume" and e.target == "act.approve.gate"
        for e in plan.edges
    )


def test_plan_without_approve_gate_does_not_require_resume_edge(tmp_path: Path) -> None:
    """Negative control: a plan without act.approve.gate is not affected.

    The fail-loud check is gated on ``act.approve.gate in node_ids``;
    plans that don't carry the gate must lift without the resume edge.
    """
    plain_yaml = tmp_path / "plain.yaml"
    plain_yaml.write_text(
        dedent(
            """\
            id: plain.subgraph
            region: act
            nodes:
              - id: act.authorize
                factory: act.authorize
                inputs: [decision]
                outputs: [decision]
              - id: act.envelope
                factory: act.envelope
                inputs: [decision]
                outputs: [envelope]
              - id: terminal.commit
                binding: terminate
                terminal: true
                inputs: [decision]
                outputs: [terminal_outcome]
            edges:
              - {from: act.authorize, to: act.envelope, when: true}
            """
        ),
        encoding="utf-8",
    )

    raw = __import__("yaml").safe_load(plain_yaml.read_text(encoding="utf-8"))
    spec = _apply_entry_fallback(raw)
    plan = lift_graph_spec(spec)
    assert "act.approve.gate" not in {n.id for n in plan.nodes}
