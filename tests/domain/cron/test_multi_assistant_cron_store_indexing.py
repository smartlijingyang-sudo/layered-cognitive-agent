"""Test MultiAssistantCronStore internal indexing and seam encapsulation (INV-ARCH-05).

Verifies O(1) job-to-assistant indexing, fast-path dispatch, on-demand index
population, index invalidation on delete, and CronRunConflictError propagation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

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


def _make_job(job_id: str, owner: str = "user_1") -> CronJob:
    return CronJob(
        id=job_id,
        title=f"Job {job_id}",
        schedule=DailySchedule(hour=9, minute=0),
        timezone="Asia/Shanghai",
        body="Periodic sync",
        execution=AgentExecution(),
        delivery_targets=(ChatDelivery(chat_id="chat_1"),),
        owner=owner,
        created_chat_id="chat_1",
        anchor_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
    )


def test_multi_assistant_cron_store_indexing_fast_path(tmp_path: Path) -> None:
    """INV-ARCH-05: list_jobs populates _job_to_assistant; get_job uses fast path."""
    asst_a = tmp_path / "asst_a"
    asst_b = tmp_path / "asst_b"
    store_a = CronStore(asst_a)
    store_b = CronStore(asst_b)

    store_a.save_job(_make_job("job_a"))
    store_b.save_job(_make_job("job_b"))

    multi = MultiAssistantCronStore(tmp_path)
    assert not multi._job_to_assistant  # Initially empty

    jobs = multi.list_jobs()
    assert {j.id for j in jobs} == {"job_a", "job_b"}
    assert multi._job_to_assistant.get("job_a") == "asst_a"
    assert multi._job_to_assistant.get("job_b") == "asst_b"

    # Fast path: resolving job_b should directly access asst_b store
    stores = multi._stores()
    store_a_inst = stores["asst_a"]
    with (
        patch.object(multi, "_stores", return_value=stores),
        patch.object(store_a_inst, "get_job") as mock_a_get,
    ):
        job = multi.get_job("job_b")
        assert job is not None
        assert job.id == "job_b"
        # store_a must NOT be queried because index routed directly to asst_b
        mock_a_get.assert_not_called()


def test_multi_assistant_cron_store_on_demand_index_population(tmp_path: Path) -> None:
    """INV-ARCH-05: get_job without prior list_jobs scans once and records mapping."""
    asst_a = tmp_path / "asst_a"
    store_a = CronStore(asst_a)
    store_a.save_job(_make_job("job_x"))

    multi = MultiAssistantCronStore(tmp_path)
    assert "job_x" not in multi._job_to_assistant

    job = multi.get_job("job_x")
    assert job is not None
    assert job.id == "job_x"
    assert multi._job_to_assistant.get("job_x") == "asst_a"


def test_multi_assistant_cron_store_conflict_propagation(tmp_path: Path) -> None:
    """INV-ARCH-05: Conflicting handoff or receipt writes raise CronRunConflictError."""
    asst_a = tmp_path / "asst_a"
    store_a = CronStore(asst_a)
    store_a.save_job(_make_job("job_sync"))

    multi = MultiAssistantCronStore(tmp_path)
    rid = multi.append_run("job_sync", outcome="completed")

    # 1. Handoff conflict check
    h1 = multi.record_handoff_runs("job_sync", rid, ("h_run_1",))
    assert h1 is not None
    assert h1.handoff_run_ids == ("h_run_1",)

    # Idempotent re-write succeeds
    h1_repeat = multi.record_handoff_runs("job_sync", rid, ("h_run_1",))
    assert h1_repeat is not None

    # Conflicting handoff raises CronRunConflictError
    with pytest.raises(CronRunConflictError):
        multi.record_handoff_runs("job_sync", rid, ("h_run_different",))

    # 2. Receipts conflict check
    rcpt1 = TargetReceipt(chat_id="chat_1", state="delivered")
    c1 = multi.close_run_receipts("job_sync", rid, (rcpt1,))
    assert c1 is not None
    assert c1.receipts == (rcpt1,)

    # Conflicting receipts raise CronRunConflictError
    rcpt_conflict = TargetReceipt(chat_id="chat_1", state="failed")
    with pytest.raises(CronRunConflictError):
        multi.close_run_receipts("job_sync", rid, (rcpt_conflict,))


def test_multi_assistant_cron_store_delete_cleans_index(tmp_path: Path) -> None:
    """INV-ARCH-05: delete_job removes job file and purges entry from _job_to_assistant."""
    asst_a = tmp_path / "asst_a"
    store_a = CronStore(asst_a)
    store_a.save_job(_make_job("job_del"))

    multi = MultiAssistantCronStore(tmp_path)
    multi.list_jobs()
    assert multi._job_to_assistant.get("job_del") == "asst_a"

    assert multi.delete_job("job_del") is True
    assert "job_del" not in multi._job_to_assistant
    assert multi.get_job("job_del") is None
    assert multi.delete_job("job_del") is False
