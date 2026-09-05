"""ExceptionIndexWriter subscriber tests (ADR-0183 / write-behind)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.infrastructure.persistence.run_buffer_registry import RunWriteBehindRegistry
from lca.plugins.events.subscribers.exception_index_writer import ExceptionIndexWriter
from lca_kernel.events import EventRef
from lca_kernel.events.payloads import SpineEventPayload


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    RunWriteBehindRegistry.reset_singleton()
    yield
    RunWriteBehindRegistry.reset_singleton()


def _ref(event_id: str = "run-exc-1:1") -> EventRef:
    return EventRef(
        event_id=event_id,
        category="spine.exception.caught",
        trace_id="run-exc-1",
        ts=1725350000.0,
        persisted=False,
        subscriber_count=0,
    )


def test_exception_index_writer_enqueues_exception_caught(tmp_path: Path) -> None:
    registry = RunWriteBehindRegistry.default()
    writer = ExceptionIndexWriter(run_dir=tmp_path, registry=registry)
    payload = SpineEventPayload(
        execution_point="exception.caught",
        channel="error",
        payload={
            "exception_class": "ValidationError",
            "exception_message": "bad payload",
            "boundary": "act.main",
        },
    )
    writer(payload, _ref())
    registry.flush_run("run-exc-1")

    exc_path = tmp_path / "run-exc-1.exceptions.jsonl"
    assert exc_path.exists()
    record = json.loads(exc_path.read_text(encoding="utf-8").strip())
    assert record["execution_point"] == "exception.caught"
    assert record["payload"]["exception_class"] == "ValidationError"


def test_exception_index_writer_ignores_non_exception_events(tmp_path: Path) -> None:
    registry = RunWriteBehindRegistry.default()
    writer = ExceptionIndexWriter(run_dir=tmp_path, registry=registry)
    payload = SpineEventPayload(
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": "s1"},
    )
    writer(payload, _ref("run-exc-2:0"))
    registry.flush_run("run-exc-2")
    assert not (tmp_path / "run-exc-2.exceptions.jsonl").exists()
