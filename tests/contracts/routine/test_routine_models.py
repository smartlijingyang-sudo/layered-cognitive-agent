"""Tests for Routine domain contract models (ADR-0248 §5.1 / s14)."""

import pytest
from pydantic import ValidationError

from lca.contracts.models.routine.models import RoutineSpec, RoutineTrigger, SpendBudget


def test_routine_spec_frozen_and_valid() -> None:
    spec = RoutineSpec(
        id="rt_check_build",
        name="检查构建日志",
        cron_expr="0 * * * *",
        prompt="检查过去一小时的构建日志，仅在发现错误时汇报",
        spend_budget_per_run=10,
        daily_budget_tokens=50_000,
        assistant_id="asst_dev",
    )
    assert spec.id == "rt_check_build"
    assert spec.cron_expr == "0 * * * *"
    assert spec.spend_budget_per_run == 10
    assert spec.enabled is True

    # 验证不可变性 (frozen=True)
    with pytest.raises(ValidationError):
        spec.name = "修改名称"  # type: ignore[misc]

    # 验证严禁额外字段 (extra="forbid")
    with pytest.raises(ValidationError):
        RoutineSpec(
            id="1",
            name="a",
            prompt="b",
            assistant_id="c",
            extra_field="forbidden",  # type: ignore[call-arg]
        )


def test_routine_spec_validation_rules() -> None:
    # prompt 不能为空
    with pytest.raises(ValidationError):
        RoutineSpec(id="rt1", name="a", prompt="", assistant_id="asst_1")

    # assistant_id 不能为空
    with pytest.raises(ValidationError):
        RoutineSpec(id="rt1", name="a", prompt="valid", assistant_id="")

    # spend_budget_per_run 必须大于 0
    with pytest.raises(ValidationError):
        RoutineSpec(id="rt1", name="a", prompt="valid", assistant_id="a1", spend_budget_per_run=0)


def test_spend_budget_model() -> None:
    budget = SpendBudget(
        daily_budget_tokens=100_000,
        max_steps_per_run=15,
        tokens_consumed_today=25_000,
    )
    assert budget.remaining_tokens_today == 75_000
    assert budget.is_exhausted is False

    budget_exhausted = SpendBudget(
        daily_budget_tokens=50_000,
        max_steps_per_run=15,
        tokens_consumed_today=55_000,
    )
    assert budget_exhausted.remaining_tokens_today == 0
    assert budget_exhausted.is_exhausted is True


def test_routine_trigger_model() -> None:
    trigger = RoutineTrigger(
        routine_id="rt_1",
        triggered_at_ms=1727160000000,
        trigger_source="cron",
    )
    assert trigger.routine_id == "rt_1"
    assert trigger.trigger_source == "cron"
    with pytest.raises(ValidationError):
        trigger.routine_id = "rt_2"  # type: ignore[misc]
