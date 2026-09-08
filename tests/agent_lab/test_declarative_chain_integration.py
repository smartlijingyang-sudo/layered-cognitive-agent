"""Declarative call-chain integration test.

Verifies that the agent_lab representation of the declarative-phase-graph
bundle is complete and consistent: every link and node declared by
``bundles/declarative-phase-graph.yaml`` is reachable through the
``agent_loop`` compile hook.

The bundle declares:
  - 6 semantic phases: perceive → think → act → reflect → remember → stop
  - 12 control-slot contributions (11 ControlSlot enum members +
    ``control.stop.focus``, a PhaseContribution attached to the stop
    phase).

This test loads the full registry (six phases + every control slot graph),
compiles agent_loop with the auto-insert control-slot hook enabled, and
asserts every required sub_spec_id is present in the resulting
``subgraph_calls``. It also verifies the manual mounts (think → mv_assemble,
act → effect_dispatch) are intact, and that the host node ports were
extended with the control-slot wiring.

The full agent_loop runner requires fixtures for perceive / think /
act / remember / stop; that is exercised by per-phase tests in
``test_{perceive,think,effect_dispatch,remember,stop}_subgraph.py``.
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


# The full set of sub_specs that must appear in agent_loop after the
# compile hook runs. Includes both the 7 manual mounts (perceive,
# assemble_for_think → mv_assemble, think, act → effect_dispatch,
# reflect, remember, stop) and the auto-inserted control slots.
EXPECTED_SUB_SPECS = {
    # Manual mounts (already in agent_loop.yaml#sub_specs).
    "perceive",
    "mv_assemble",
    "think",
    "effect_dispatch",
    "reflect",
    "remember",
    "stop",
    # Control slots — owner-bound (10 slots from the LCA bundle + the
    # non-ControlSlot stop.focus contribution).
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
    # Cross-cutting observers (LCA OBSERVE_CHECKPOINT + OBSERVE_WILDCARD).
    "observe_checkpoint",
    "observe_wildcard",
}


def test_full_declarative_chain_wires_through_compile_hook() -> None:
    """Load the full registry; compile agent_loop; assert every sub_spec
    from the declarative bundle is present in the resulting bundle."""
    specs = load_registry(
        # Six phase sub-graphs.
        "perceive",
        "think",
        "reflect",
        "remember",
        "stop",
        # mv_assemble + effect_dispatch (mounted by agent_loop).
        "mv_assemble",
        "effect_dispatch",
        # Agent loop root.
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
    """A profile that omits the control_slots plugin keeps only the 7
    manual mounts."""
    specs = load_registry(
        "perceive",
        "think",
        "reflect",
        "remember",
        "stop",
        "mv_assemble",
        "effect_dispatch",
        "agent_loop",
    )

    # Strip the control_slots plugin so before_compile doesn't insert anything.
    from agent_lab.graph.spec import PluginRef  # noqa: F401

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
        "mv_assemble",
        "think",
        "effect_dispatch",
        "reflect",
        "remember",
        "stop",
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
        "stop",
        "mv_assemble",
        "effect_dispatch",
        "agent_loop",
    )
    # Trigger the plugin manually so we can inspect the mutated spec.
    plugin = ControlSlotsPlugin(name="control_slots", kind="control_slots")
    mutated = plugin.before_compile(specs["agent_loop"], specs)
    host_by_id = {n.id: n for n in mutated.nodes}

    # act host carries 5 act.* control slots → 5 act_*_allowed output ports
    act_host = host_by_id["act"]
    for slot_name in (
        "act_authorize_allowed",
        "act_budget_allowed",
        "act_constrain_allowed",
        "act_execute_allowed",
        "act_safe_boundary_allowed",
    ):
        assert slot_name in act_host.outs, (
            f"act host missing {slot_name} in outs; has {act_host.outs}"
        )

    # stop host carries stop_decide (stop_decision, terminal) + stop_focus
    # (focus_verdict).
    stop_host = host_by_id["stop"]
    for port_name in ("stop_decision", "terminal", "focus_verdict"):
        assert port_name in stop_host.outs, (
            f"stop host missing {port_name} in outs; has {stop_host.outs}"
        )

    # perceive host carries perceive_context → perceive_context_allowed
    perceive_host = host_by_id["perceive"]
    assert "perceive_context_allowed" in perceive_host.outs

    # observe_* slots are cross-cutting; every phase host gets them.
    observe_out_keys = (
        "checkpoint_event",  # observe.checkpoint output
        "wildcard_event",    # observe.* output
    )
    for host_id in ("perceive", "think", "act", "reflect", "remember", "stop"):
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
