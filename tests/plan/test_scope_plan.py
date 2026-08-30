"""Tests for ScopePlan + BudgetCeiling (ADR-0068 §一 + ADR-0074 PR-3 最小版)."""

from __future__ import annotations

import pytest

from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.scope_plan import (
    BudgetCeiling,
    ScopePlan,
    scope_plan_from_iter,
    scope_plan_hash,
    scope_plan_to_dict,
)


class TestBudgetCeiling:
    def test_default_is_all_none(self) -> None:
        b = BudgetCeiling()
        assert b.max_tokens is None
        assert b.max_wall_clock_seconds is None
        assert b.max_tool_calls is None
        assert b.max_steps is None
        assert b.max_cost_cents is None

    def test_with_values(self) -> None:
        b = BudgetCeiling(max_tokens=10000, max_wall_clock_seconds=3600, max_steps=50)
        assert b.max_tokens == 10000
        assert b.max_wall_clock_seconds == 3600
        assert b.max_steps == 50

    def test_negative_max_tokens_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_tokens must be non-negative"):
            BudgetCeiling(max_tokens=-1)

    def test_string_max_steps_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_steps must be non-negative"):
            BudgetCeiling(max_steps="50")  # type: ignore[arg-type]


class TestScopePlanConstruction:
    def test_minimal(self) -> None:
        plan = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        assert plan.profile_path == "x.yaml"
        assert plan.lifecycle is Scope.RUN
        assert plan.visibility == ()
        assert plan.acl_grants == ()
        assert plan.revision == "v1"

    def test_blank_profile_rejected(self) -> None:
        with pytest.raises(ValueError, match="profile_path must be non-empty"):
            ScopePlan(
                profile_path="",
                lifecycle=Scope.RUN,
                visibility=(),
                acl_grants=(),
                budget_ceiling=BudgetCeiling(),
            )

    def test_str_lifecycle_normalized(self) -> None:
        plan = ScopePlan(
            profile_path="x.yaml",
            lifecycle="run",
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        assert plan.lifecycle is Scope.RUN

    def test_visibility_deduped_and_sorted(self) -> None:
        plan = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(Scope.RUN, Scope.AGENT, Scope.RUN, Scope.PROFILE),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        # 3 unique values: PROFILE, AGENT, RUN; sorted by Scope enum order
        assert plan.visibility == (Scope.PROFILE, Scope.AGENT, Scope.RUN)

    def test_visibility_normalizes_str_inputs(self) -> None:
        plan = ScopePlan(
            profile_path="x.yaml",
            lifecycle="run",
            visibility=("run", "agent", "run"),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        # 3 unique Scope values; sorted by enum order
        assert Scope.RUN in plan.visibility
        assert Scope.AGENT in plan.visibility


class TestScopePlanHash:
    def test_empty_plan_hash_stable(self) -> None:
        plan = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        h1 = scope_plan_hash(plan)
        h2 = scope_plan_hash(plan)
        assert h1 == h2
        assert len(h1) == 16

    def test_different_profile_yields_different_hash(self) -> None:
        plan1 = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        plan2 = ScopePlan(
            profile_path="y.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        assert scope_plan_hash(plan1) != scope_plan_hash(plan2)

    def test_different_lifecycle_yields_different_hash(self) -> None:
        plan1 = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        plan2 = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.AGENT,
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        assert scope_plan_hash(plan1) != scope_plan_hash(plan2)

    def test_acl_grants_order_invariance(self) -> None:
        plan1 = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=("a", "b", "c"),
            budget_ceiling=BudgetCeiling(),
        )
        plan2 = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=("c", "b", "a"),
            budget_ceiling=BudgetCeiling(),
        )
        assert scope_plan_hash(plan1) == scope_plan_hash(plan2)


class TestScopePlanAccessors:
    def test_to_dict(self) -> None:
        plan = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(Scope.AGENT, Scope.RUN),
            acl_grants=("cap.x",),
            budget_ceiling=BudgetCeiling(max_steps=10),
        )
        d = scope_plan_to_dict(plan)
        assert d["profile_path"] == "x.yaml"
        assert d["lifecycle"] == "run"
        assert d["visibility"] == ["agent", "run"]
        assert d["acl_grants"] == ["cap.x"]
        assert d["budget_ceiling"]["max_steps"] == 10
        assert d["plan_hash"] == scope_plan_hash(plan)

    def test_from_iter_with_dict_budget(self) -> None:
        plan = scope_plan_from_iter(
            lifecycle=Scope.RUN,
            visibility=(Scope.RUN,),
            acl_grants=("cap.x",),
            budget_ceiling={"max_steps": 10},
            profile_path="x.yaml",
        )
        assert plan.budget_ceiling.max_steps == 10

    def test_from_iter_with_none_budget(self) -> None:
        plan = scope_plan_from_iter(
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=(),
            budget_ceiling=None,
            profile_path="x.yaml",
        )
        assert plan.budget_ceiling.max_steps is None
        assert plan.profile_path == "x.yaml"
