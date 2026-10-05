"""ADR-0268 §6.1: one run record, two fields completed exactly once.

``handoff_run_ids`` is written before the handoff run starts so a crash between
the two cannot make recovery dispatch the same occurrence twice. ``receipts`` is
closed when the handoff turn ends. Both are idempotent on identical values and
reject different ones, because a second, different value is a contradiction
rather than an update.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    CronRunConflictError,
    DailySchedule,
    TargetReceipt,
)
from lca.domain.cron.store import CronStore, MultiAssistantCronStore

_FINISHED = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
_RUN_ID = "job_daily-abc123"
_DELIVERED = (TargetReceipt(chat_id="tpc_1", state="delivered"),)
_SILENT = (TargetReceipt(chat_id=None, state="silent"),)


@pytest.fixture
def store(tmp_path: Path) -> CronStore:
    s = CronStore(tmp_path / "assistant_home")
    s.save_job(
        CronJob(
            id="job_daily",
            title="每天提醒",
            body="站起来走走",
            schedule=DailySchedule(hour=9, minute=0),
            timezone="Asia/Shanghai",
            execution=AgentExecution(),
            owner="asst_1",
            created_chat_id="tpc_1",
            delivery_targets=(ChatDelivery(chat_id="tpc_1"),),
            anchor_at=datetime(2026, 10, 1, 1, 0, tzinfo=UTC),
        )
    )
    s.append_run(
        "job_daily",
        run_id=_RUN_ID,
        outcome="completed",
        receipts=(),
        finished_at=_FINISHED,
    )
    return s


def test_a_record_written_before_this_change_reads_as_undispatched(store: CronStore) -> None:
    """No migration: an absent field means the handoff was never dispatched."""
    path = store._runs_dir("job_daily") / f"{_RUN_ID}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["handoff_run_ids"]
    path.write_text(json.dumps(raw), encoding="utf-8")

    run = store.get_run("job_daily", _RUN_ID)

    assert run is not None
    assert run.handoff_run_ids == ()
    assert run.receipts == ()


def test_handoff_ids_land_on_a_pending_record(store: CronStore) -> None:
    updated = store.record_handoff_runs("job_daily", _RUN_ID, ("run_h1",))

    assert updated is not None
    assert updated.handoff_run_ids == ("run_h1",)
    assert updated.receipts == ()
    assert store.get_run("job_daily", _RUN_ID).handoff_run_ids == ("run_h1",)


def test_the_append_only_fields_survive_both_completions(store: CronStore) -> None:
    store.record_handoff_runs("job_daily", _RUN_ID, ("run_h1",))
    closed = store.close_run_receipts("job_daily", _RUN_ID, _DELIVERED)

    assert closed is not None
    assert closed.run_id == _RUN_ID
    assert closed.outcome == "completed"
    assert closed.finished_at == _FINISHED
    assert closed.receipts == _DELIVERED
    assert closed.handoff_run_ids == ("run_h1",)


def test_rewriting_the_same_ids_is_a_no_op(store: CronStore) -> None:
    first = store.record_handoff_runs("job_daily", _RUN_ID, ("run_h1", "run_h2"))
    second = store.record_handoff_runs("job_daily", _RUN_ID, ("run_h1", "run_h2"))

    assert first == second


def test_a_different_set_of_ids_is_a_contradiction(store: CronStore) -> None:
    store.record_handoff_runs("job_daily", _RUN_ID, ("run_h1",))

    with pytest.raises(CronRunConflictError):
        store.record_handoff_runs("job_daily", _RUN_ID, ("run_other",))

    assert store.get_run("job_daily", _RUN_ID).handoff_run_ids == ("run_h1",)


def test_closing_receipts_once_makes_the_record_decided(store: CronStore) -> None:
    closed = store.close_run_receipts("job_daily", _RUN_ID, _SILENT)

    assert closed is not None
    assert closed.receipts == _SILENT


def test_reclosing_with_the_same_receipts_is_a_no_op(store: CronStore) -> None:
    store.close_run_receipts("job_daily", _RUN_ID, _SILENT)

    assert store.close_run_receipts("job_daily", _RUN_ID, _SILENT).receipts == _SILENT


def test_reclosing_with_different_receipts_is_a_contradiction(store: CronStore) -> None:
    store.close_run_receipts("job_daily", _RUN_ID, _SILENT)

    with pytest.raises(CronRunConflictError):
        store.close_run_receipts("job_daily", _RUN_ID, _DELIVERED)

    assert store.get_run("job_daily", _RUN_ID).receipts == _SILENT


def test_completing_an_unknown_run_returns_none(store: CronStore) -> None:
    assert store.record_handoff_runs("job_daily", "run_missing", ("r",)) is None
    assert store.close_run_receipts("job_daily", "run_missing", _DELIVERED) is None


def test_the_multi_assistant_proxy_routes_to_the_owning_home(tmp_path: Path) -> None:
    home = tmp_path / "assistants" / "asst_1"
    inner = CronStore(home)
    inner.save_job(
        CronJob(
            id="job_daily",
            title="每天提醒",
            body="站起来走走",
            schedule=DailySchedule(hour=9, minute=0),
            timezone="Asia/Shanghai",
            execution=AgentExecution(),
            owner="asst_1",
            created_chat_id="tpc_1",
            delivery_targets=(ChatDelivery(chat_id="tpc_1"),),
            anchor_at=datetime(2026, 10, 1, 1, 0, tzinfo=UTC),
        )
    )
    inner.append_run("job_daily", run_id=_RUN_ID, outcome="completed", finished_at=_FINISHED)
    multi = MultiAssistantCronStore(tmp_path / "assistants")

    assert multi.record_handoff_runs("job_daily", _RUN_ID, ("run_h1",)).handoff_run_ids == (
        "run_h1",
    )
    assert multi.close_run_receipts("job_daily", _RUN_ID, _DELIVERED).receipts == _DELIVERED
    assert multi.record_handoff_runs("job_unknown", _RUN_ID, ("r",)) is None
    assert multi.close_run_receipts("job_unknown", _RUN_ID, _DELIVERED) is None
