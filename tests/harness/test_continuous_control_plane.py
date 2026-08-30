from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lca.contracts.harness.command import CommandReceipt
from lca.contracts.harness.continuous import (
    Trigger,
    TriggerKind,
    WorkActivationReceipt,
    WorkItem,
    WorkStatus,
)
from lca.harness.continuous import SqliteContinuousControlPlane, SqliteWorkQueue
from lca.harness.continuous_session import AgentRegistryWorkActivator

NOW = datetime(2026, 8, 27, 0, 0, tzinfo=UTC)


def _item(
    *,
    work_id: str = "work-1",
    trigger_id: str = "trigger-1",
    max_attempts: int = 3,
    session_id: str | None = None,
) -> WorkItem:
    return WorkItem(
        work_id=work_id,
        trigger=Trigger(
            trigger_id=trigger_id,
            kind=TriggerKind.EVENT,
            occurred_at=NOW,
            subject="repository.changed",
        ),
        profile="web-standard" if session_id is None else None,
        session_id=session_id,
        message="review the new commit",
        max_attempts=max_attempts,
    )


def _queue(tmp_path: Path) -> SqliteWorkQueue:
    return SqliteWorkQueue(tmp_path / "continuous.db")


def test_submit_deduplicates_by_immutable_work_and_trigger_identity(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    original = _item()
    duplicate = _item(work_id="work-2")

    assert queue.submit(original) == original
    assert queue.submit(duplicate) == original
    assert queue.get("work-1") == original
    assert queue.get("work-2") is None
    assert queue.status_of("work-1") is WorkStatus.PENDING


def test_claim_is_exclusive_and_expired_lease_can_be_recovered(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    queue.submit(_item())

    first = queue.claim("worker-a", now=NOW, lease_seconds=10)
    assert first is not None
    assert queue.claim("worker-b", now=NOW + timedelta(seconds=1), lease_seconds=10) is None

    recovered = queue.claim("worker-b", now=NOW + timedelta(seconds=11), lease_seconds=10)
    assert recovered is not None
    assert recovered.worker_id == "worker-b"
    assert recovered.attempt == 2


def test_release_retries_then_dead_letters_at_declared_attempt_limit(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    queue.submit(_item(max_attempts=2))

    first = queue.claim("worker-a", now=NOW, lease_seconds=10)
    assert first is not None
    assert (
        queue.release(first, now=NOW, retry_delay_seconds=5, detail="transient")
        is WorkStatus.RETRY_WAIT
    )
    assert queue.claim("worker-b", now=NOW + timedelta(seconds=4), lease_seconds=10) is None

    second = queue.claim("worker-b", now=NOW + timedelta(seconds=5), lease_seconds=10)
    assert second is not None
    assert (
        queue.release(second, now=NOW + timedelta(seconds=5), retry_delay_seconds=5, detail="again")
        is WorkStatus.DEAD
    )
    assert queue.status_of("work-1") is WorkStatus.DEAD


@pytest.mark.asyncio
async def test_control_plane_releases_failed_activation_then_acks_a_successful_retry(
    tmp_path: Path,
) -> None:
    now = [NOW]
    queue = _queue(tmp_path)
    plane = SqliteContinuousControlPlane(
        queue=queue,
        lease_seconds=10,
        retry_delay_seconds=5,
        clock=lambda: now[0],
    )
    plane.submit(_item())

    class RejectingActivator:
        async def activate(self, item: WorkItem) -> WorkActivationReceipt:
            assert item.work_id == "work-1"
            return WorkActivationReceipt(accepted=False, detail="upstream busy")

    class AcceptingActivator:
        async def activate(self, item: WorkItem) -> WorkActivationReceipt:
            return WorkActivationReceipt(accepted=True, session_id="ses-1", detail="queued")

    assert await plane.run_once("worker-a", RejectingActivator()) is not None
    assert queue.status_of("work-1") is WorkStatus.RETRY_WAIT
    now[0] = NOW + timedelta(seconds=5)
    assert await plane.run_once("worker-b", AcceptingActivator()) is not None
    assert queue.status_of("work-1") is WorkStatus.DISPATCHED


@pytest.mark.asyncio
async def test_control_plane_releases_claim_when_worker_is_cancelled(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    plane = SqliteContinuousControlPlane(queue=queue, clock=lambda: NOW)
    plane.submit(_item())

    class CancelledActivator:
        async def activate(self, item: WorkItem) -> WorkActivationReceipt:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await plane.run_once("worker-a", CancelledActivator())
    assert queue.status_of("work-1") is WorkStatus.RETRY_WAIT


@pytest.mark.asyncio
async def test_agent_registry_activator_uses_stable_session_and_message_id() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class Registry:
        async def create_session(self, **kwargs: object) -> CommandReceipt:
            calls.append(("create", kwargs))
            return CommandReceipt("create", str(kwargs["session_id"]), 1, True)

        async def dispatch_message(self, **kwargs: object) -> CommandReceipt:
            calls.append(("dispatch", kwargs))
            return CommandReceipt("dispatch", str(kwargs["session_id"]), 2, True)

        async def cancel(self, **kwargs: object) -> CommandReceipt:
            raise AssertionError("not used")

        async def resume_approval(self, **kwargs: object) -> CommandReceipt:
            raise AssertionError("not used")

        async def steer(self, **kwargs: object) -> CommandReceipt:
            raise AssertionError("not used")

        async def inject(self, **kwargs: object) -> CommandReceipt:
            raise AssertionError("not used")

    receipt = await AgentRegistryWorkActivator(Registry()).activate(_item())

    assert receipt == WorkActivationReceipt(True, "ses-work-work-1", "work_dispatched")
    assert calls == [
        (
            "create",
            {
                "idempotency_key": "continuous:create:work-1",
                "profile": "web-standard",
                "preset": None,
                "options": None,
                "session_id": "ses-work-work-1",
            },
        ),
        (
            "dispatch",
            {
                "session_id": "ses-work-work-1",
                "idempotency_key": "continuous:dispatch:work-1",
                "content": "review the new commit",
                "role": "user",
                "message_id": "msg-work-work-1",
            },
        ),
    ]
