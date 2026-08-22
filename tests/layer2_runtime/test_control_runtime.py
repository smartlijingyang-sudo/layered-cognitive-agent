from __future__ import annotations

import pytest

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.control_plan import (
    Activation,
    AggregationMode,
    ControlEntry,
    ControlPlan,
    compute_control_plan_hash,
)
from lca.layer2_runtime.control_runtime import (
    ControlVerdict,
    ControlVerdictKind,
    aggregate_control_verdicts,
    evaluate_control,
    select_control_entries,
)


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


def _entry(
    plugin_id: str,
    slot: ControlSlot,
    *,
    order: int = 100,
    aggregation: AggregationMode | None = None,
) -> ControlEntry:
    return ControlEntry(
        plugin_id=plugin_id,
        slot=slot,
        order=order,
        aggregation=aggregation,
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


@pytest.mark.parametrize(
    ("slot", "verdicts", "expected"),
    (
        (
            ControlSlot.ACT_AUTHORIZE,
            (
                ControlVerdict("first", ControlVerdictKind.ALLOW),
                ControlVerdict("second", ControlVerdictKind.DENY),
            ),
            ControlVerdictKind.DENY,
        ),
        (
            ControlSlot.ACT_BUDGET,
            (
                ControlVerdict("first", ControlVerdictKind.ALLOW),
                ControlVerdict("second", ControlVerdictKind.EXHAUSTED),
            ),
            ControlVerdictKind.EXHAUSTED,
        ),
        (
            ControlSlot.STOP_DECIDE,
            (
                ControlVerdict("first", ControlVerdictKind.ALLOW),
                ControlVerdict("second", ControlVerdictKind.STOP),
            ),
            ControlVerdictKind.STOP,
        ),
        (
            ControlSlot.THINK_GUARD,
            (
                ControlVerdict("first", ControlVerdictKind.REWRITE),
                ControlVerdict("second", ControlVerdictKind.ASK_HUMAN),
                ControlVerdict("third", ControlVerdictKind.STOP),
            ),
            ControlVerdictKind.STOP,
        ),
    ),
)
def test_evaluate_control_applies_monotonic_slot_aggregation(
    slot: ControlSlot,
    verdicts: tuple[ControlVerdict, ...],
    expected: ControlVerdictKind,
) -> None:
    entries = tuple(
        _entry(verdict.plugin_id, slot, order=index) for index, verdict in enumerate(verdicts)
    )

    evaluation = evaluate_control(_plan(entries), slot, _state(), verdicts=verdicts)

    assert evaluation.effective is not None
    assert evaluation.effective.kind is expected


def test_decision_priority_is_strict_stop_ask_human_rewrite_allow() -> None:
    entries = (
        _entry("allow", ControlSlot.THINK_GUARD, order=10),
        _entry("rewrite", ControlSlot.THINK_GUARD, order=20),
        _entry("ask", ControlSlot.THINK_GUARD, order=30),
    )
    evaluation = evaluate_control(
        _plan(entries),
        ControlSlot.THINK_GUARD,
        _state(),
        verdicts=(
            ControlVerdict("allow", ControlVerdictKind.ALLOW),
            ControlVerdict("rewrite", ControlVerdictKind.REWRITE),
            ControlVerdict("ask", ControlVerdictKind.ASK_HUMAN),
        ),
    )

    assert evaluation.effective is not None
    assert evaluation.effective.kind is ControlVerdictKind.ASK_HUMAN


def test_no_aggregate_slots_preserve_independent_contributions() -> None:
    plan = _plan((_entry("checkpoint", ControlSlot.OBSERVE_CHECKPOINT),))

    evaluation = evaluate_control(
        plan,
        ControlSlot.OBSERVE_CHECKPOINT,
        _state(),
        verdicts=(ControlVerdict("checkpoint", ControlVerdictKind.DENY),),
    )

    assert evaluation.aggregation is AggregationMode.NO_AGGREGATE
    assert evaluation.effective is None
    assert evaluation.verdicts[0].kind is ControlVerdictKind.DENY


def test_conflicting_entry_aggregation_is_rejected() -> None:
    plan = _plan(
        (
            _entry(
                "one",
                ControlSlot.ACT_AUTHORIZE,
                aggregation=AggregationMode.DENY_ON_ANY_DENY,
            ),
            _entry(
                "two",
                ControlSlot.ACT_AUTHORIZE,
                aggregation=AggregationMode.NO_AGGREGATE,
            ),
        )
    )
    selection = select_control_entries(plan, ControlSlot.ACT_AUTHORIZE, _state())

    with pytest.raises(ValueError, match="conflicting aggregation modes"):
        aggregate_control_verdicts(selection)


def test_verdicts_for_inactive_plugins_are_rejected() -> None:
    plan = _plan((_entry("active", ControlSlot.ACT_AUTHORIZE),))

    with pytest.raises(ValueError, match="inactive or unknown plugins"):
        evaluate_control(
            plan,
            ControlSlot.ACT_AUTHORIZE,
            _state(),
            verdicts=(ControlVerdict("other", ControlVerdictKind.DENY),),
        )


def test_all_eleven_slots_have_one_evaluation_entry_point() -> None:
    entries = tuple(_entry(f"plugin.{slot.name.lower()}", slot) for slot in ControlSlot)
    plan = _plan(entries)

    evaluations = [evaluate_control(plan, slot, _state()) for slot in ControlSlot]

    assert [evaluation.selection.slot for evaluation in evaluations] == list(ControlSlot)
    assert all(len(evaluation.selection.entries) == 1 for evaluation in evaluations)
