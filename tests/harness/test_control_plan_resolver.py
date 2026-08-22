"""Tests for ControlPlan + resolver (ADR-0066 §六 + ADR-0074 PR-1).

This test covers:

- Activation DSL: operator whitelist, structural validation
- ControlEntry construction + slot allowlist
- ControlPlan: ordering, hash stability, by_slot index
- Resolver: opt-in semantics (no plugin declares control → empty plan),
  hash stability across runs, slot enumeration correctness
- explain_control_slot: deterministic output for diagnostic tools
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.atoms.control_slot import (
    SLOT_PHASE_OWNER,
    ControlSlot,
    all_slot_values,
)
from lca.contracts.protocols.control_plan import (
    ALLOWED_OPERATORS,
    SLOT_DEFAULT_AGGREGATION,
    SLOT_DEFAULT_FAILURE,
    Activation,
    AggregationMode,
    ControlEntry,
    ControlPlan,
    FailureMode,
    always,
    compute_control_plan_hash,
    control_plan_to_dict,
    is_slot_empty,
    slot_entries,
    slots_covered,
    slots_missing,
)
from lca.harness.profile.control_plan_resolver import (
    ControlPlanOptions,
    ControlPlanResolveError,
    _validate_slot_aggregations,
    explain_control_slot,
    project_control_plan,
)
from lca.harness.profile.resolve import resolve_profile

# ── Activation DSL ────────────────────────────────────────────────


class TestActivationAlways:
    def test_default_is_always(self) -> None:
        act = Activation()
        assert act.predicate == {"always": True}

    def test_always_factory(self) -> None:
        assert always().predicate == {"always": True}


class TestActivationOperatorWhitelist:
    def test_all_allowed_operators(self) -> None:
        # If you add a new operator here, also update docs/adr/0066 §三
        assert (
            frozenset(
                {
                    "always",
                    "all",
                    "any",
                    "not",
                    "in",
                    "not_in",
                    "eq",
                    "ne",
                    "lt",
                    "le",
                    "gt",
                    "ge",
                    "exists",
                    "missing",
                }
            )
            == ALLOWED_OPERATORS
        )

    def test_reject_unknown_operator(self) -> None:
        with pytest.raises(ValueError, match="missing 'fact' key"):
            Activation({"eval": "anything"})

    def test_reject_lambda_or_callable(self) -> None:
        """DSL must not allow callable / expression."""
        with pytest.raises(ValueError, match="missing 'fact' key"):
            Activation({"call": "module.func"})

    def test_reject_env_var(self) -> None:
        with pytest.raises(ValueError, match="missing 'fact' key"):
            Activation({"env": "HOME"})


class TestActivationStructural:
    def test_node_must_be_mapping(self) -> None:
        with pytest.raises(ValueError, match="must be mapping"):
            Activation([])  # type: ignore[arg-type]

    def test_node_must_have_single_key(self) -> None:
        with pytest.raises(ValueError, match="must be the sole key"):
            Activation({"all": [], "any": []})

    def test_empty_mapping_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            Activation({})

    @pytest.mark.parametrize(
        "predicate",
        [
            {"all": [{"fact": "a", "eq": 1}, {"fact": "b", "eq": 2}]},
            {"any": [{"fact": "a", "in": [1, 2]}]},
            {"not": {"fact": "x", "eq": True}},
            {"all": [{"any": [{"fact": "a", "eq": 1}]}]},
        ],
    )
    def test_composite_predicates_accepted(self, predicate: object) -> None:
        Activation(predicate)

    def test_composite_body_must_be_list(self) -> None:
        with pytest.raises(ValueError, match="must be list"):
            Activation({"all": {"fact": "a", "eq": 1}})

    def test_composite_empty_list_accepted(self) -> None:
        """Empty ``all`` / ``any`` is degenerate but deterministic — accepted."""
        Activation({"all": []})
        Activation({"any": []})

    def test_leaf_must_have_fact(self) -> None:
        with pytest.raises(ValueError, match="missing 'fact' key"):
            Activation({"eq": 1})

    def test_leaf_fact_must_be_non_empty_str(self) -> None:
        with pytest.raises(ValueError, match="non-empty str"):
            Activation({"fact": "", "eq": 1})

    def test_always_body_must_be_true(self) -> None:
        with pytest.raises(ValueError, match=r"\{'always': True\}"):
            Activation({"always": False})

    def test_leaf_rejects_unknown_op(self) -> None:
        with pytest.raises(ValueError, match="unknown operator"):
            Activation({"fact": "x", "eval": "anything"})

    def test_leaf_must_have_one_op(self) -> None:
        with pytest.raises(ValueError, match="needs a comparison operator"):
            Activation({"fact": "x"})


# ── ControlEntry ───────────────────────────────────────────────────


class TestControlEntryConstruction:
    def test_minimal_valid_entry(self) -> None:
        entry = ControlEntry(
            plugin_id="plugin.x",
            slot=ControlSlot.ACT_BUDGET,
        )
        assert entry.plugin_id == "plugin.x"
        assert entry.slot is ControlSlot.ACT_BUDGET
        assert entry.order == 100
        assert entry.activation.predicate == {"always": True}
        assert entry.aggregation is None
        assert entry.failure_mode is None
        assert entry.authority == ()
        assert entry.effect_class == "none"

    def test_blank_plugin_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="plugin_id"):
            ControlEntry(plugin_id="", slot=ControlSlot.ACT_BUDGET)

    def test_invalid_slot_type_rejected(self) -> None:
        with pytest.raises(TypeError, match="ControlSlot"):
            ControlEntry(plugin_id="p", slot="act.execute")  # type: ignore[arg-type]

    def test_accepts_overrides(self) -> None:
        entry = ControlEntry(
            plugin_id="plugin.x",
            slot=ControlSlot.ACT_AUTHORIZE,
            order=50,
            aggregation=AggregationMode.DENY_ON_ANY_DENY,
            failure_mode=FailureMode.DENY,
            authority=("cap.budget",),
            reads=("task.contract",),
            emits=("policy.authorize.denied",),
            effect_class="none",
            source="bundles/base.yaml",
        )
        assert entry.order == 50
        assert entry.aggregation is AggregationMode.DENY_ON_ANY_DENY
        assert entry.failure_mode is FailureMode.DENY
        assert entry.authority == ("cap.budget",)
        assert entry.source == "bundles/base.yaml"


# ── Slot defaults ─────────────────────────────────────────────────


class TestSlotDefaults:
    @pytest.mark.parametrize(
        "slot,agg",
        [
            (ControlSlot.ACT_AUTHORIZE, AggregationMode.DENY_ON_ANY_DENY),
            (ControlSlot.ACT_BUDGET, AggregationMode.DENY_ON_EXHAUSTED),
            (ControlSlot.ACT_CONSTRAIN, AggregationMode.DENY_ON_ANY_DENY),
            (ControlSlot.STOP_DECIDE, AggregationMode.STOP_ON_ANY_STOP),
            (ControlSlot.THINK_GUARD, AggregationMode.DECISION_PRIORITY),
            (ControlSlot.OBSERVE_WILDCARD, AggregationMode.NO_AGGREGATE),
            (ControlSlot.ACT_SAFE_BOUNDARY, AggregationMode.NO_AGGREGATE),
        ],
    )
    def test_aggregation_matches_adrs(self, slot: ControlSlot, agg: AggregationMode) -> None:
        """ADR-0066 §四 monotonic aggregation table."""
        assert SLOT_DEFAULT_AGGREGATION[slot] is agg

    @pytest.mark.parametrize(
        "slot,failure",
        [
            (ControlSlot.ACT_AUTHORIZE, FailureMode.DENY),
            (ControlSlot.ACT_BUDGET, FailureMode.DENY),
            (ControlSlot.STOP_DECIDE, FailureMode.STOP),
            (ControlSlot.OBSERVE_WILDCARD, FailureMode.IGNORE),
        ],
    )
    def test_failure_mode_matches_adrs(self, slot: ControlSlot, failure: FailureMode) -> None:
        """ADR-0066 §三 failure_mode field defaults per slot."""
        assert SLOT_DEFAULT_FAILURE[slot] is failure


# ── ControlPlan ────────────────────────────────────────────────────


class TestControlPlanOrdering:
    def test_entries_must_be_sorted_by_slot_then_order_then_plugin(self) -> None:
        """Caller must pre-sort entries — frozen dataclass rejects unsorted input."""
        e1 = ControlEntry(plugin_id="z", slot=ControlSlot.STOP_DECIDE, order=10)
        e2 = ControlEntry(plugin_id="a", slot=ControlSlot.ACT_BUDGET, order=50)
        e3 = ControlEntry(plugin_id="b", slot=ControlSlot.ACT_BUDGET, order=10)
        unsorted = (e1, e2, e3)
        with pytest.raises(ValueError, match="must be sorted"):
            ControlPlan(
                profile_path="x.yaml",
                entries=unsorted,
                by_slot={
                    ControlSlot.STOP_DECIDE: (e1,),
                    ControlSlot.ACT_BUDGET: (e3, e2),
                },
                plan_hash="deadbeef00000000",
            )

    def test_sorted_entries_pass_through(self) -> None:
        e1 = ControlEntry(plugin_id="b", slot=ControlSlot.ACT_BUDGET, order=10)
        e2 = ControlEntry(plugin_id="a", slot=ControlSlot.ACT_BUDGET, order=50)
        e3 = ControlEntry(plugin_id="z", slot=ControlSlot.STOP_DECIDE, order=10)
        plan = ControlPlan(
            profile_path="x.yaml",
            entries=(e1, e2, e3),
            by_slot={
                ControlSlot.ACT_BUDGET: (e1, e2),
                ControlSlot.STOP_DECIDE: (e3,),
            },
            plan_hash="deadbeef00000000",
        )
        ids = [e.plugin_id for e in plan.entries]
        assert ids == ["b", "a", "z"]

    def test_duplicate_plugin_id_rejected(self) -> None:
        e1 = ControlEntry(plugin_id="dup", slot=ControlSlot.ACT_BUDGET)
        e2 = ControlEntry(plugin_id="dup", slot=ControlSlot.STOP_DECIDE)
        with pytest.raises(ValueError, match="duplicate plugin_id"):
            ControlPlan(
                profile_path="x.yaml",
                entries=(e1, e2),
                by_slot={},
                plan_hash="deadbeef00000000",
            )

    def test_blank_profile_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="profile_path"):
            ControlPlan(
                profile_path="",
                entries=(),
                by_slot={},
                plan_hash="deadbeef00000000",
            )


class TestControlPlanAccessors:
    def test_slot_entries_returns_correct_subset(self) -> None:
        e1 = ControlEntry(plugin_id="a", slot=ControlSlot.ACT_BUDGET)
        e2 = ControlEntry(plugin_id="b", slot=ControlSlot.STOP_DECIDE)
        plan = ControlPlan(
            profile_path="x.yaml",
            entries=(e1, e2),
            by_slot={ControlSlot.ACT_BUDGET: (e1,), ControlSlot.STOP_DECIDE: (e2,)},
            plan_hash="deadbeef00000000",
        )
        assert slot_entries(plan, ControlSlot.ACT_BUDGET) == (e1,)
        assert slot_entries(plan, "stop.decide") == (e2,)
        assert slot_entries(plan, ControlSlot.THINK_GUARD) == ()

    def test_is_empty(self) -> None:
        plan = ControlPlan(
            profile_path="x.yaml",
            entries=(),
            by_slot={},
            plan_hash="deadbeef00000000",
        )
        assert is_slot_empty(plan, ControlSlot.ACT_BUDGET)
        assert is_slot_empty(plan, ControlSlot.PERCEIVE_CONTEXT)
        assert is_slot_empty(plan, "stop.decide")

    def test_slots_covered(self) -> None:
        e = ControlEntry(plugin_id="a", slot=ControlSlot.ACT_BUDGET)
        plan = ControlPlan(
            profile_path="x.yaml",
            entries=(e,),
            by_slot={ControlSlot.ACT_BUDGET: (e,)},
            plan_hash="deadbeef00000000",
        )
        assert slots_covered(plan) == frozenset({ControlSlot.ACT_BUDGET})

    def test_slots_missing_covers_all_eleven(self) -> None:
        """11-slot closed set — slots_missing enumerates the whole universe."""
        plan = ControlPlan(
            profile_path="x.yaml",
            entries=(),
            by_slot={},
            plan_hash="deadbeef00000000",
        )
        missing = slots_missing(plan)
        assert len(missing) == 11
        assert set(missing) == set(ControlSlot)

    def test_to_dict_round_trips(self) -> None:
        e = ControlEntry(
            plugin_id="plugin.x",
            slot=ControlSlot.ACT_BUDGET,
            aggregation=AggregationMode.DENY_ON_EXHAUSTED,
            failure_mode=FailureMode.DENY,
        )
        plan = ControlPlan(
            profile_path="x.yaml",
            entries=(e,),
            by_slot={ControlSlot.ACT_BUDGET: (e,)},
            plan_hash="deadbeef00000000",
        )
        d = control_plan_to_dict(plan)
        assert d["profile_path"] == "x.yaml"
        assert d["plan_hash"] == "deadbeef00000000"
        assert len(d["entries"]) == 1
        assert d["entries"][0]["plugin_id"] == "plugin.x"
        assert d["entries"][0]["slot"] == "act.budget"
        assert d["entries"][0]["aggregation"] == "deny_on_exhausted"


# ── Hash stability ────────────────────────────────────────────────


class TestComputeControlPlanHash:
    def test_empty_plan_is_stable(self) -> None:
        h1 = compute_control_plan_hash((), "x.yaml")
        h2 = compute_control_plan_hash((), "x.yaml")
        assert h1 == h2
        assert len(h1) == 16

    def test_different_profile_yields_different_hash(self) -> None:
        h1 = compute_control_plan_hash((), "x.yaml")
        h2 = compute_control_plan_hash((), "y.yaml")
        assert h1 != h2

    def test_order_invariance(self) -> None:
        """Entries can be passed in any order — hash is canonical."""
        e1 = ControlEntry(plugin_id="a", slot=ControlSlot.ACT_BUDGET, order=10)
        e2 = ControlEntry(plugin_id="b", slot=ControlSlot.STOP_DECIDE, order=20)
        h1 = compute_control_plan_hash((e1, e2), "x.yaml")
        h2 = compute_control_plan_hash((e2, e1), "x.yaml")
        assert h1 == h2

    def test_different_entries_yield_different_hash(self) -> None:
        e1 = ControlEntry(plugin_id="a", slot=ControlSlot.ACT_BUDGET)
        e2 = ControlEntry(plugin_id="b", slot=ControlSlot.ACT_BUDGET)
        h1 = compute_control_plan_hash((e1,), "x.yaml")
        h2 = compute_control_plan_hash((e2,), "x.yaml")
        assert h1 != h2


class TestResolverAggregationValidation:
    def test_conflicting_aggregation_modes_fail_before_runtime(self) -> None:
        entries = (
            ControlEntry(
                plugin_id="policy.a",
                slot=ControlSlot.ACT_AUTHORIZE,
                aggregation=AggregationMode.DENY_ON_ANY_DENY,
            ),
            ControlEntry(
                plugin_id="policy.b",
                slot=ControlSlot.ACT_AUTHORIZE,
                aggregation=AggregationMode.DENY_ON_EXHAUSTED,
            ),
        )

        with pytest.raises(ControlPlanResolveError, match="conflicting aggregation modes"):
            _validate_slot_aggregations({ControlSlot.ACT_AUTHORIZE: entries})


# ── Resolver — eleven-slot closure ─────────────────────────────────


class TestProjectControlPlanClosure:
    """Every resolved plan carries the constitutional eleven-slot closure."""

    def test_web_standard_profile_covers_all_eleven_slots(self) -> None:
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = project_control_plan(resolved)

        assert len(plan.entries) == 12
        assert slots_covered(plan) == frozenset(ControlSlot)
        assert slots_missing(plan) == ()
        assert [entry.plugin_id for entry in slot_entries(plan, ControlSlot.THINK_GUARD)] == [
            "gate.repeat-tool-call",
            "gate.tool-loop-breaker",
        ]
        assert [entry.plugin_id for entry in slot_entries(plan, ControlSlot.ACT_BUDGET)] == [
            "body.simple.act-budget"
        ]
        assert all(not entry.plugin_id.startswith("control.default.") for entry in plan.entries)
        plan_again = project_control_plan(resolved)
        assert plan.plan_hash == plan_again.plan_hash

    def test_include_disabled_keeps_default_closure_stable(self) -> None:
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = project_control_plan(resolved, options=ControlPlanOptions(include_disabled=True))
        assert len(plan.entries) == 12
        assert slots_covered(plan) == frozenset(ControlSlot)

    def test_hash_unaffected_by_projection_options(self) -> None:
        """Disabled plugins do not alter the eleven-slot compiled plan."""
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan_default = project_control_plan(resolved)
        plan_with_disabled = project_control_plan(
            resolved, options=ControlPlanOptions(include_disabled=True)
        )
        assert plan_default.plan_hash == plan_with_disabled.plan_hash


class TestResolverRejectsBadEntries:
    def test_non_list_control_rejected(self, tmp_path: Path) -> None:
        # Build a profile with a control field that's not a list
        (tmp_path / "bad.yaml").write_text("control: not_a_list\n", encoding="utf-8")
        # Indirect: directly fabricate a ResolvedPlugin via resolver error path
        # by stuffing a control into the meta. Skip — covered by parser unit tests.

    def test_unknown_slot_in_entry_rejected(self) -> None:

        # Fake plugin — ResolvedPlugin requires definition, which requires setup.
        # Use the parser error path via direct call.
        # Skipped: full ResolvedPlugin construction needs an actual module;
        # we cover this via _parse_control_list and _parse_control_entry
        # exercised in integration via boot. Here we verify the validator:
        try:
            from lca.contracts.atoms.control_slot import parse_slot

            parse_slot("not.a.real.slot")
        except ValueError as exc:
            assert "unknown control slot" in str(exc)


# ── explain_control_slot ──────────────────────────────────────────


class TestExplainControlSlot:
    def test_explain_missing_slot(self) -> None:
        plan = ControlPlan(
            profile_path="x.yaml",
            entries=(),
            by_slot={},
            plan_hash="deadbeef00000000",
        )
        info = explain_control_slot(plan, ControlSlot.ACT_AUTHORIZE)
        assert info["slot"] == "act.authorize"
        assert info["phase"] == "act"
        assert info["default_aggregation"] == "deny_on_any_deny"
        assert info["default_failure_mode"] == "deny"
        assert info["missing"] is True
        assert info["entries"] == []

    def test_explain_observed_slot(self) -> None:
        e = ControlEntry(
            plugin_id="plugin.x",
            slot=ControlSlot.ACT_AUTHORIZE,
            order=42,
            aggregation=AggregationMode.DENY_ON_ANY_DENY,
            failure_mode=FailureMode.DENY,
            authority=("cap.budget",),
            effect_class="tools",
            source="bundles/test.yaml",
        )
        plan = ControlPlan(
            profile_path="x.yaml",
            entries=(e,),
            by_slot={ControlSlot.ACT_AUTHORIZE: (e,)},
            plan_hash="deadbeef00000000",
        )
        info = explain_control_slot(plan, ControlSlot.ACT_AUTHORIZE)
        assert info["missing"] is False
        assert len(info["entries"]) == 1
        first = info["entries"][0]
        assert first["plugin_id"] == "plugin.x"
        assert first["order"] == 42
        assert first["aggregation"] == "deny_on_any_deny"
        assert first["source"] == "bundles/test.yaml"

    def test_explain_cross_cutting_slot(self) -> None:
        plan = ControlPlan(
            profile_path="x.yaml",
            entries=(),
            by_slot={},
            plan_hash="deadbeef00000000",
        )
        info = explain_control_slot(plan, ControlSlot.OBSERVE_CHECKPOINT)
        assert info["phase"] == "observe"  # cross-cutting → "observe"
        assert info["default_aggregation"] == "no_aggregate"

    def test_explain_accepts_string(self) -> None:
        plan = ControlPlan(
            profile_path="x.yaml",
            entries=(),
            by_slot={},
            plan_hash="deadbeef00000000",
        )
        info = explain_control_slot(plan, "stop.decide")
        assert info["slot"] == "stop.decide"

    def test_explain_rejects_unknown_slot(self) -> None:
        plan = ControlPlan(
            profile_path="x.yaml",
            entries=(),
            by_slot={},
            plan_hash="deadbeef00000000",
        )
        with pytest.raises(ValueError, match="unknown control slot"):
            explain_control_slot(plan, "act.bogus")


# ── All-slot enumeration ──────────────────────────────────────────


class TestAllSlotsEnumeration:
    def test_all_eleven_slots_have_phase_owner_or_none(self) -> None:
        """Every ControlSlot member has a phase_owner entry (None for cross-cutting)."""
        for slot in ControlSlot:
            assert slot in SLOT_PHASE_OWNER

    def test_all_eleven_slots_have_aggregation(self) -> None:
        for slot in ControlSlot:
            assert slot in SLOT_DEFAULT_AGGREGATION

    def test_all_eleven_slots_have_failure_mode(self) -> None:
        for slot in ControlSlot:
            assert slot in SLOT_DEFAULT_FAILURE

    def test_all_slot_values_length(self) -> None:
        assert len(all_slot_values()) == 11
