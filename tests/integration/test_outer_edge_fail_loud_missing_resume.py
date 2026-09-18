"""Validator acceptance — outer plan must consume approval_routing.

The full-restart HITL resume design (driver.py restarts from perceive.main)
does not require an ``intervene.resume → act.approve.gate`` edge. The
validator now checks that the outer plan consumes ``approval_routing.next_hint``
via edge predicates so approve-interrupt and approve-rejected outcomes
have somewhere to land.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from lca.framework.graph.lifter import lift_graph_spec


def _apply_entry_fallback(mapping):
    """Mirror ``_apply_entry_fallback`` from ``lca_kernel.boot.plan_validation``."""
    spec = dict(mapping)
    nodes = list(spec.get("nodes") or ())
    if nodes and not any(
        isinstance(n, dict) and n.get("entry") for n in nodes
    ):
        nodes[0] = {**nodes[0], "entry": True}
        spec["nodes"] = nodes
    return spec


def test_outer_plan_must_consume_approval_routing(tmp_path: Path) -> None:
    """Outer plan with act.main but no approval_routing consumer → PlanLiftError."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        dedent(
            """\
            id: bad.outer
            region: agent
            nodes:
              - id: act.main
                region: phase:act
                sub_spec_ref:
                  plan_ref: bundles/act/act_subgraph.yaml
                  entry_node: act.validate
                  binding_edge: act.main
                declared_inputs: [decision]
                declared_outputs: [decision, should_terminate, approval_routing]
              - id: terminal.commit
                region: phase:terminal
                binding: terminate
                terminal: true
                declared_inputs: [decision]
                declared_outputs: [terminal_outcome]
            edges:
              - {from: act.main, to: terminal.commit, when: true}
            """
        ),
        encoding="utf-8",
    )

    raw = __import__("yaml").safe_load(bad_yaml.read_text(encoding="utf-8"))
    spec = _apply_entry_fallback(raw)

    with pytest.raises(Exception) as exc:
        lift_graph_spec(spec)
    message = str(exc.value)
    assert "approval_routing" in message, (
        "validator must reference approval_routing in the failure message; got: " + message
    )


def test_outer_plan_with_approval_routing_consumer_passes_lift(tmp_path: Path) -> None:
    """Negative control: outer plan that consumes approval_routing lifts cleanly."""
    good_yaml = tmp_path / "good.yaml"
    good_yaml.write_text(
        dedent(
            """\
            id: good.outer
            region: agent
            nodes:
              - id: act.main
                region: phase:act
                sub_spec_ref:
                  plan_ref: bundles/act/act_subgraph.yaml
                  entry_node: act.validate
                  binding_edge: act.main
                declared_inputs: [decision]
                declared_outputs: [decision, should_terminate, approval_routing]
              - id: terminal.commit
                region: phase:terminal
                binding: terminate
                terminal: true
                declared_inputs: [decision]
                declared_outputs: [terminal_outcome]
            edges:
              - from: act.main
                to: terminal.commit
                when:
                  kind: eq
                  port: { name: approval_routing, field: next_hint }
                  value: approve_rejected
            """
        ),
        encoding="utf-8",
    )

    raw = __import__("yaml").safe_load(good_yaml.read_text(encoding="utf-8"))
    spec = _apply_entry_fallback(raw)
    plan = lift_graph_spec(spec)
    assert any(n.id == "act.main" for n in plan.nodes)


def test_plan_without_approve_gate_does_not_require_routing_consumer(tmp_path: Path) -> None:
    """Negative control: a plan without act.main/approve.gate is not affected."""
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
