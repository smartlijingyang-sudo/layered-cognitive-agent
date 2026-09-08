"""Declarative call-chain integration test.

Verifies that the agent_lab representation of the declarative-phase-graph
bundle is complete and consistent: every link and node declared by
``bundles/declarative-phase-graph.yaml`` is reachable through the
``agent_loop`` compile hook.

The agent_lab root declares:
  - 5 cognitive phase hosts: perceive → think → act → reflect → remember
  - stop as control slots on remember (stop_decide / stop_focus)
  - other control-slot contributions (act.* data-plane grant is in act.yaml;
    control/act_* are not auto-inserted).

This test loads the full registry, compiles agent_loop with the
control-slot hook enabled, and asserts required sub_spec_ids appear in
``subgraph_calls``. Manual mounts (perceive → model_eye, act) stay intact.

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

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Manual cognitive mounts + auto-inserted control slots.
# Act data-plane grant lives in act.yaml; control/act_* are not inserted.
EXPECTED_SUB_SPECS = {
    # Manual mounts (already in agent_loop.yaml#sub_specs).
    # model_eye is nested under perceive, not a direct agent_loop mount.
    "perceive",
    "think",
    "act",
    "reflect",
    "remember",
    # Control slots — owner-bound (stop_* attach on remember).
    "perceive_context",
    "think_guard",
    "remember_admit",
    "stop_decide",
    "stop_focus",
    # Cross-cutting observers (LCA OBSERVE_CHECKPOINT + OBSERVE_WILDCARD).
    "observe_checkpoint",
    "observe_wildcard",
}


def test_full_declarative_chain_wires_through_compile_hook() -> None:
    """Load the full registry; compile agent_loop; assert every sub_spec
    from the declarative bundle is present in the resulting bundle."""
    specs = load_registry(
        "perceive",
        "think",
        "reflect",
        "remember",
        "model_eye",
        "act",
        "agent_loop",
    )

    bundle = compile_spec(specs["agent_loop"], sub_registry=specs)

    inserted = {x["sub_spec_id"] for x in bundle.subgraph_calls}
    missing = EXPECTED_SUB_SPECS - inserted
    assert not missing, (
        f"compile hook missed declarative chain sub_specs: {sorted(missing)}\n"
        f"present: {sorted(inserted)}"
    )


def test_compile_hook_disabled_leaves_only_manual_mounts() -> None:
    """A profile that omits the control_slots plugin keeps only the 5
    manual mounts."""
    specs = load_registry(
        "perceive",
        "think",
        "reflect",
        "remember",
        "model_eye",
        "act",
        "agent_loop",
    )

    stripped_plugins = [
        p for p in specs["agent_loop"].plugins if p.kind != "control_slots"
    ]
    specs["agent_loop"] = specs["agent_loop"].model_copy(
        update={"plugins": stripped_plugins}
    )

    bundle = compile_spec(specs["agent_loop"], sub_registry=specs)

    inserted = {x["sub_spec_id"] for x in bundle.subgraph_calls}
    expected_manual = {
        "perceive",
        "think",
        "act",
        "reflect",
        "remember",
    }
    assert inserted == expected_manual


def test_control_slot_wiring_extends_host_node_ports() -> None:
    """The control_slots plugin extends each phase host's ins/outs to
    include the wiring ports (so the sub_spec call has ports to
    read/write)."""
    from agent_lab.plugins.control_slots import ControlSlotsPlugin

    specs = load_registry(
        "perceive",
        "think",
        "reflect",
        "remember",
        "model_eye",
        "act",
        "agent_loop",
    )
    plugin = ControlSlotsPlugin(name="control_slots", kind="control_slots")
    mutated = plugin.before_compile(specs["agent_loop"], specs)
    host_by_id = {n.id: n for n in mutated.nodes}

    assert "stop" not in host_by_id

    # act host: grant is in-band (act.authorize); only observer ports added.
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

    # remember host carries stop_decide (stop_decision, terminal) + stop_focus
    # (focus_verdict) after persist.
    remember_host = host_by_id["remember"]
    for port_name in ("stop_decision", "terminal", "focus_verdict"):
        assert port_name in remember_host.outs, (
            f"remember host missing {port_name} in outs; has {remember_host.outs}"
        )

    # perceive host carries perceive_context → perceive_context_allowed
    perceive_host = host_by_id["perceive"]
    assert "perceive_context_allowed" in perceive_host.outs

    # observe_* slots are cross-cutting; every cognitive phase host gets them.
    observe_out_keys = (
        "checkpoint_event",
        "wildcard_event",
    )
    for host_id in ("perceive", "think", "act", "reflect", "remember"):
        host = host_by_id[host_id]
        for port in observe_out_keys:
            assert port in host.outs, (
                f"{host_id} host missing cross-cutting observer port {port}; "
                f"has {host.outs}"
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
