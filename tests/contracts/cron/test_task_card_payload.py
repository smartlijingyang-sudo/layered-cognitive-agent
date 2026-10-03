"""Tests for CronTaskCardWidgetPayload contract (Task 1)."""

import pytest
from pydantic import ValidationError

from lca.contracts.models.cron.card import (
    CronTaskCardAction,
    CronTaskCardWidgetPayload,
    parse_cron_task_card_widget,
    serialize_cron_task_card_widget,
)


def test_cron_task_card_widget_payload_valid():
    payload = CronTaskCardWidgetPayload(
        job_id="test-job-001",
        title="提醒喝水",
        body="李超，记得喝水！",
        schedule_label="一次性 2026-10-03 22:00",
        next_run_local="2026-10-03 22:00",
        delayed_by_seconds=120,
    )
    assert payload.job_id == "test-job-001"
    assert payload.title == "提醒喝水"
    assert payload.delayed_by_seconds == 120
    assert payload.widget_name == "cron_task_card"
    assert "snooze" in payload.actions

    # Immutability
    with pytest.raises(ValidationError):
        payload.title = "改标题"  # type: ignore[misc]


def test_cron_task_card_serialization_roundtrip():
    payload = CronTaskCardWidgetPayload(
        job_id="test-job-002",
        title="晨会提醒",
        body="准备 ADR 评审",
        schedule_label="每天 09:30",
        next_run_local="2026-10-04 09:30",
        execution_kind="agent",
        actions=(
            CronTaskCardAction.SNOOZE.value,
            CronTaskCardAction.EDIT.value,
            CronTaskCardAction.DELETE.value,
        ),
    )
    serialized = serialize_cron_task_card_widget(payload)
    assert "[widget:cron_task_card]" in serialized
    assert "[/widget:cron_task_card]" in serialized

    parsed = parse_cron_task_card_widget(serialized)
    assert parsed is not None
    assert parsed.job_id == "test-job-002"
    assert parsed.title == "晨会提醒"
    assert parsed.schedule_label == "每天 09:30"
    assert parsed.actions == ("snooze", "edit", "delete")


def test_parse_cron_task_card_widget_invalid():
    assert parse_cron_task_card_widget("普通文本消息没有 widget") is None
    assert parse_cron_task_card_widget("[widget:cron_task_card]{invalid json}[/widget:cron_task_card]") is None
