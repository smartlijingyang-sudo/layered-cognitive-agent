"""Declarative call-chain integration test.

Verifies that the agent_lab representation of the declarative-phase-graph
bundle is complete and consistent: every link and node declared by
``bundles/declarative-phase-graph.yaml`` is reachable through the
``agent_loop`` compile hook.

The agent_lab root declares:
  - 5 cognitive phase hosts: perceive → think → act → reflect → remember
  - stop / think_guard / remember_admit / perceive_context as sibling hosts
  - act.* data-plane grant is in act.yaml; control/act_* are not mounted.

This test loads the agent_loop closure, compiles it, and asserts required
sub_spec_ids appear in ``subgraph_calls``. Nested mounts (perceive →
model_eye, act) stay intact.

The full agent_loop runner requires fixtures for perceive / think /
act / remember; that is exercised by per-phase tests in
``test_{perceive,think,act,remember,stop}_subgraph.py``.
This test focuses on the topology / wiring aspect.
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.graphs.loader import load_closure

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Cognitive mounts + sibling control hosts declared in agent_loop.yaml.
# Act data-plane grant lives in act.yaml; control/act_* are not mounted.
# observe_* omitted: no in_event_log / in_event producer on phase hosts.
EXPECTED_SUB_SPECS = {
    "perceive",
    "think",
    "act",
    "reflect",
    "remember",
    "perceive_context",
    "think_guard",
    "remember_admit",
    "stop_decide",
    "stop_focus",
}


def test_full_declarative_chain_wires_through_compile_hook() -> None:
    """Load the agent_loop closure; compile; assert every sibling sub_spec."""
    specs = load_closure("agent_loop")

    bundle = compile_spec(specs["agent_loop"], sub_registry=specs)

    inserted = {x["sub_spec_id"] for x in bundle.subgraph_calls}
    missing = EXPECTED_SUB_SPECS - inserted
    assert not missing, (
        f"agent_loop yaml missed declarative chain sub_specs: {sorted(missing)}\n"
        f"present: {sorted(inserted)}"
    )


def test_compile_hook_disabled_leaves_only_manual_mounts() -> None:
    """Stripping a retired control_slots plugin still leaves YAML sibling hosts."""
    specs = load_closure("agent_loop")

    stripped_plugins = [p for p in specs["agent_loop"].plugins if p.kind != "control_slots"]
    specs["agent_loop"] = specs["agent_loop"].model_copy(update={"plugins": stripped_plugins})

    bundle = compile_spec(specs["agent_loop"], sub_registry=specs)

    inserted = {x["sub_spec_id"] for x in bundle.subgraph_calls}
    assert inserted == EXPECTED_SUB_SPECS


def test_control_slot_wiring_extends_host_node_ports() -> None:
    """Sibling control hosts declare their own ports; phase hosts stay data-plane."""
    specs = load_closure("agent_loop")
    host_by_id = {n.id: n for n in specs["agent_loop"].nodes}

    assert "stop" not in host_by_id
    assert "stop_decide" in host_by_id
    assert "stop_focus" in host_by_id
    assert "think_guard" in host_by_id
    assert "perceive_context" in host_by_id
    assert "remember_admit" in host_by_id

    act_host = host_by_id["act"]
    for slot_name in (
        "act_authorize_allowed",
        "act_budget_allowed",
        "act_constrain_allowed",
        "act_execute_allowed",
        "act_safe_boundary_allowed",
    ):
        assert slot_name not in act_host.outs, (
            f"act host must not expose unused control port {slot_name}; has {act_host.outs}"
        )

    remember_host = host_by_id["remember"]
    for port_name in ("stop_decision", "terminal", "focus_verdict"):
        assert port_name not in remember_host.outs, (
            f"remember host must not own {port_name}; has {remember_host.outs}"
        )

    stop_decide = host_by_id["stop_decide"]
    assert "stop_decision" in stop_decide.outs
    assert "terminal" in stop_decide.outs
    assert "state_ref" in stop_decide.ins

    perceive_host = host_by_id["perceive"]
    assert "perceive_context_allowed" not in perceive_host.outs
    assert "allowed" in host_by_id["perceive_context"].outs

    observe_out_keys = ("checkpoint_event", "wildcard_event")
    for host_id in ("perceive", "think", "act", "reflect", "remember"):
        host = host_by_id[host_id]
        for port in observe_out_keys:
            assert port not in host.outs, (
                f"{host_id} host must not invent observer port {port}; has {host.outs}"
            )


def test_control_slot_subgraphs_compile_independently() -> None:
    """Every control slot subgraph listed in the declarative bundle
    compiles cleanly when loaded standalone."""
    slot_ids = [
        "perceive_context",
        "think_guard",
        "act_authorize",
        "act_budget",
        "act_constrain",
        "act_execute",
        "act_safe_boundary",
        "remember_admit",
        "stop_decide",
        "stop_focus",
        "observe_checkpoint",
        "observe_wildcard",
    ]
    specs = load_registry(*slot_ids)
    assert set(specs.keys()) == set(slot_ids)
    for slot_id, spec in specs.items():
        bundle = compile_spec(spec, sub_registry=specs)
        assert bundle.spec_id == slot_id
        assert bundle.plan_hash  # non-empty hash
        assert bundle.layers  # at least one topological layer
