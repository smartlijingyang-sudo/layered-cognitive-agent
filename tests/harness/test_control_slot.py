"""Tests for ControlSlot enum (ADR-0066 §二 + tracker §19)."""

from __future__ import annotations

import pytest

from lca.contracts.atoms.control_slot import (
    SLOT_PHASE_OWNER,
    ControlSlot,
    all_slot_values,
    as_phase_label,
    is_cross_cutting,
    parse_slot,
    phase_owner,
    validate_slot_iterable,
)


class TestControlSlotEnum:
    def test_has_exactly_eleven_members(self) -> None:
        """11 slots = 9 (ADR-0066 §二) + 2 (tracker §19.1 observe.checkpoint + act.safe-boundary)."""
        members = list(ControlSlot)
        assert len(members) == 11

    def test_canonical_values_match_adrs(self) -> None:
        """Slot values are stable string literals; any change is a wire break."""
        assert ControlSlot.PERCEIVE_CONTEXT.value == "perceive.context"
        assert ControlSlot.THINK_GUARD.value == "think.guard"
        assert ControlSlot.ACT_AUTHORIZE.value == "act.authorize"
        assert ControlSlot.ACT_BUDGET.value == "act.budget"
        assert ControlSlot.ACT_CONSTRAIN.value == "act.constrain"
        assert ControlSlot.ACT_EXECUTE.value == "act.execute"
        assert ControlSlot.ACT_SAFE_BOUNDARY.value == "act.safe-boundary"
        assert ControlSlot.REMEMBER_ADMIT.value == "remember.admit"
        assert ControlSlot.STOP_DECIDE.value == "stop.decide"
        assert ControlSlot.OBSERVE_CHECKPOINT.value == "observe.checkpoint"
        assert ControlSlot.OBSERVE_WILDCARD.value == "observe.*"

    def test_str_enum_value_equality(self) -> None:
        """str Enum allows ``ControlSlot.X == "x.y"`` — useful for serialization."""
        assert ControlSlot.ACT_EXECUTE == "act.execute"

    def test_no_duplicate_values(self) -> None:
        values = [s.value for s in ControlSlot]
        assert len(values) == len(set(values)), "duplicate slot strings"

    def test_all_slot_values_returns_all(self) -> None:
        values = all_slot_values()
        assert len(values) == 11
        assert "perceive.context" in values
        assert "observe.*" in values


class TestPhaseOwner:
    @pytest.mark.parametrize(
        "slot,expected",
        [
            (ControlSlot.PERCEIVE_CONTEXT, "perceive"),
            (ControlSlot.THINK_GUARD, "think"),
            (ControlSlot.ACT_AUTHORIZE, "act"),
            (ControlSlot.ACT_BUDGET, "act"),
            (ControlSlot.ACT_CONSTRAIN, "act"),
            (ControlSlot.ACT_EXECUTE, "act"),
            (ControlSlot.ACT_SAFE_BOUNDARY, "act"),
            (ControlSlot.REMEMBER_ADMIT, "memory"),
            (ControlSlot.STOP_DECIDE, "stop"),
        ],
    )
    def test_in_pipeline_phase_owner(self, slot: ControlSlot, expected: str) -> None:
        assert phase_owner(slot) == expected

    @pytest.mark.parametrize(
        "slot",
        [ControlSlot.OBSERVE_CHECKPOINT, ControlSlot.OBSERVE_WILDCARD],
    )
    def test_observe_slots_have_no_phase_owner(self, slot: ControlSlot) -> None:
        """Tracker §19.1: observe.* are cross-cutting observers, not C1 phases."""
        assert phase_owner(slot) is None

    def test_phase_owner_consistent_with_dict(self) -> None:
        for slot in ControlSlot:
            assert SLOT_PHASE_OWNER[slot] == phase_owner(slot)


class TestIsCrossCutting:
    def test_observe_slots_are_cross_cutting(self) -> None:
        assert is_cross_cutting(ControlSlot.OBSERVE_CHECKPOINT)
        assert is_cross_cutting(ControlSlot.OBSERVE_WILDCARD)

    @pytest.mark.parametrize(
        "slot",
        [
            ControlSlot.PERCEIVE_CONTEXT,
            ControlSlot.THINK_GUARD,
            ControlSlot.ACT_AUTHORIZE,
            ControlSlot.ACT_BUDGET,
            ControlSlot.ACT_CONSTRAIN,
            ControlSlot.ACT_EXECUTE,
            ControlSlot.ACT_SAFE_BOUNDARY,
            ControlSlot.REMEMBER_ADMIT,
            ControlSlot.STOP_DECIDE,
        ],
    )
    def test_pipeline_slots_not_cross_cutting(self, slot: ControlSlot) -> None:
        assert not is_cross_cutting(slot)


class TestAsPhaseLabel:
    def test_pipeline_slot_returns_phase(self) -> None:
        assert as_phase_label(ControlSlot.ACT_EXECUTE) == "act"
        assert as_phase_label(ControlSlot.STOP_DECIDE) == "stop"

    def test_observe_slot_returns_observe(self) -> None:
        assert as_phase_label(ControlSlot.OBSERVE_CHECKPOINT) == "observe"
        assert as_phase_label(ControlSlot.OBSERVE_WILDCARD) == "observe"


class TestParseSlot:
    def test_round_trip_string(self) -> None:
        for slot in ControlSlot:
            assert parse_slot(slot.value) is slot

    def test_round_trip_enum(self) -> None:
        for slot in ControlSlot:
            assert parse_slot(slot) is slot

    def test_unknown_string_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown control slot"):
            parse_slot("think.before_everything")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_slot("")

    def test_non_string_raises(self) -> None:
        with pytest.raises(TypeError):
            parse_slot(42)


class TestValidateSlotIterable:
    def test_valid_list(self) -> None:
        result = validate_slot_iterable(["act.authorize", "act.budget", "stop.decide"])
        assert result == (
            ControlSlot.ACT_AUTHORIZE,
            ControlSlot.ACT_BUDGET,
            ControlSlot.STOP_DECIDE,
        )

    def test_valid_tuple(self) -> None:
        result = validate_slot_iterable(("perceive.context",))
        assert result == (ControlSlot.PERCEIVE_CONTEXT,)

    def test_empty_iterable_returns_empty(self) -> None:
        assert validate_slot_iterable([]) == ()
        assert validate_slot_iterable(()) == ()

    def test_non_iterable_raises(self) -> None:
        with pytest.raises(ValueError, match="must be list/tuple"):
            validate_slot_iterable("act.execute")

    def test_unknown_member_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown control slot"):
            validate_slot_iterable(["act.execute", "act.bogus"])

    def test_dict_raises(self) -> None:
        """Dict is iterable but not list/tuple — must reject explicitly."""
        with pytest.raises(ValueError, match="must be list/tuple"):
            validate_slot_iterable({"slot": "act.execute"})


class TestAuditSurfaceDriftGuard:
    """Audit module must derive its slot set from the enum — no manual drift."""

    def test_audit_known_slots_matches_enum(self) -> None:
        from lca.harness.diagnostics.audit_control_surface import (
            KNOWN_CONTROL_SLOTS,
        )

        assert frozenset(all_slot_values()) == KNOWN_CONTROL_SLOTS
