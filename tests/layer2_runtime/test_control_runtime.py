from __future__ import annotations

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.control_plan import (
    Activation,
    ControlEntry,
    ControlPlan,
    compute_control_plan_hash,
)
from lca.layer2_runtime.control_runtime import select_control_entries


def _state(*, step: int = 0) -> AgentState:
    return AgentState(trace_id="trace", task="task", budget=create_budget(max_steps=4), step=step)


def _plan(entries: tuple[ControlEntry, ...]) -> ControlPlan:
    ordered = tuple(
        sorted(entries, key=lambda entry: (entry.slot.value, entry.order, entry.plugin_id))
    )
    by_slot: dict[ControlSlot, tuple[ControlEntry, ...]] = {}
    for entry in ordered:
        by_slot[entry.slot] = (*by_slot.get(entry.slot, ()), entry)
    return ControlPlan(
        profile_path="profiles/test.yaml",
        entries=ordered,
        by_slot=by_slot,
        plan_hash=compute_control_plan_hash(ordered, "profiles/test.yaml"),
    )


def test_select_control_entries_uses_plan_slot_order_and_activation() -> None:
    plan = _plan(
        (
            ControlEntry(plugin_id="late", slot=ControlSlot.THINK_GUARD, order=20),
            ControlEntry(
                plugin_id="active",
                slot=ControlSlot.THINK_GUARD,
                order=10,
                activation=Activation({"fact": "state.step", "eq": 2}),
            ),
            ControlEntry(
                plugin_id="inactive",
                slot=ControlSlot.THINK_GUARD,
                order=5,
                activation=Activation({"fact": "state.step", "gt": 2}),
            ),
        )
    )

    selection = select_control_entries(plan, ControlSlot.THINK_GUARD, _state(step=2))

    assert [entry.plugin_id for entry in selection.entries] == ["active", "late"]
    assert selection.facts["state.step"] == 2


def test_select_control_entries_returns_empty_for_uncovered_slot() -> None:
    selection = select_control_entries(_plan(()), ControlSlot.ACT_BUDGET, _state())

    assert selection.entries == ()
