"""Durable HIL restart-recovery regression tests.

A run paused at ``WAITING_INPUT`` must survive a kernel restart: the pause
writes ``resume_bundle.json`` (``write_resume_bundle``), and an answer that
arrives after the restart lazily rebuilds the run session from that bundle
(``restore_waiting_run``).  These tests pin the bundle round-trip and the
no-op / idempotent edges of the recovery path.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from lca.contracts.models.core.state.state import StateSnapshot
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseRunCursor,
)
from lca.plugins.transport.webserver.carrier.runs.recovery import (
    load_resume_bundle,
    restore_waiting_run,
    write_resume_bundle,
)
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunLifecycleStatus,
    RunSession,
)
from lca.plugins.transport.webserver.read.runs.identity import AgentRef


def _paused_session(run_id: str = "run-rec-1") -> RunSession:
    session = RunSession(
        run_id=run_id,
        trace_id="trace-rec-1",
        spine_path=Path("traces/rec.spine.jsonl"),
        tail=MagicMock(name="tail"),
        question="山还是海？",
        user_text="用 askUserQuestion 只问一题。",
        mode="solo",
    )
    session.status = RunLifecycleStatus.WAITING_INPUT
    session.plan_ref = "plan-ref-1"
    session.snapshot = StateSnapshot(
        snapshot_id="snap-1",
        step=0,
        state_ref="mem://trace-rec-1/0",
        phase_cursor=PhaseRunCursor(
            plan_ref="plan-ref-1",
            node_id="intervene.interrupt",
            visit_counts=(("think.main", 2),),
            edge_counts=(),
            artifacts={},
            causation_refs=(),
            budget_snapshot={},
        ),
        trace_id="trace-rec-1",
        run_id=run_id,
    )
    session.approval_request = {
        "approval_id": "plan-ref-1:intervene.interrupt:1",
        "type": "ask_user_question",
        "questions": [
            {
                "question": "山还是海？",
                "header": "选择",
                "options": [
                    {"label": "山", "description": "巍峨高山"},
                    {"label": "海", "description": "浩瀚大海"},
                ],
            }
        ],
        "tool_calls": [
            {
                "call_id": "toolu_abc",
                "tool_name": "askUserQuestion",
                "arguments": {"questions": [{"question": "山还是海？"}]},
            }
        ],
    }
    session.agent = AgentRef(agent_id="solo", name="助手")
    session.device_id = ""
    session.plane = ""
    session.extra_plane = ""
    session.execution_target = ""
    session.assistant_id = ""
    session.user_id = "u1"
    session.topic_id = "tpc-1"
    session.origin = "user"
    session.developer_seed = ""
    session.developer_seed_job_id = ""
    session.attachment_ids = ()
    session.started_at = 1000.0
    session.locator = MagicMock(name="locator")
    session.locator.run_dir.return_value = Path("traces") / run_id
    return session


def test_write_and_load_resume_bundle(tmp_path: Path) -> None:
    run_dir = tmp_path / "traces" / "run-rec-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    session = _paused_session()
    session.locator.run_dir.return_value = run_dir

    write_resume_bundle(session)

    bundle_path = run_dir / "resume_bundle.json"
    assert bundle_path.is_file()
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert bundle["schema"] == "lca.run.resume_bundle/1"
    assert bundle["run_id"] == "run-rec-1"
    assert bundle["trace_id"] == "trace-rec-1"
    assert bundle["topic_id"] == "tpc-1"
    assert bundle["user_id"] == "u1"
    assert bundle["approval_request"]["approval_id"] == "plan-ref-1:intervene.interrupt:1"
    assert bundle["resume_point"]["approval_id"] == "plan-ref-1:intervene.interrupt:1"
    assert bundle["resume_point"]["state_ref"] == "mem://trace-rec-1/0"

    loaded = load_resume_bundle("run-rec-1", session.locator)
    assert loaded == bundle


def test_load_resume_bundle_missing_returns_none(tmp_path: Path) -> None:
    locator = MagicMock(name="locator")
    locator.run_dir.return_value = tmp_path / "nope"
    assert load_resume_bundle("run-missing", locator) is None


def test_write_resume_bundle_skips_without_snapshot(tmp_path: Path) -> None:
    run_dir = tmp_path / "traces" / "run-rec-2"
    run_dir.mkdir(parents=True, exist_ok=True)
    session = _paused_session(run_id="run-rec-2")
    session.locator.run_dir.return_value = run_dir
    session.snapshot = None

    write_resume_bundle(session)

    assert not (run_dir / "resume_bundle.json").exists()


async def test_restore_waiting_run_missing_bundle_returns_none() -> None:
    registry = MagicMock(name="registry")
    locator = MagicMock(name="locator")
    locator.run_dir.return_value = Path("traces/run-missing")
    registry.locator.return_value = locator

    result = await restore_waiting_run(registry, ctx=object(), run_id="run-missing")
    assert result is None


async def test_restore_waiting_run_reuses_existing_session(tmp_path: Path) -> None:
    session = _paused_session()
    registry = MagicMock(name="registry")
    locator = MagicMock(name="locator")
    run_dir = tmp_path / "traces" / "run-rec-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "resume_bundle.json").write_text(
        json.dumps({"schema": "lca.run.resume_bundle/1", "run_id": "run-rec-1"}),
        encoding="utf-8",
    )
    locator.run_dir.return_value = run_dir
    registry.locator.return_value = locator
    registry.get.return_value = session

    result = await restore_waiting_run(registry, ctx=object(), run_id="run-rec-1")
    assert result is session


def test_bundle_write_failure_is_contained(tmp_path: Path) -> None:
    """A paused run must not fail because the bundle cannot be written."""
    session = _paused_session()
    session.locator = None  # no locator -> best-effort skip, no raise
    write_resume_bundle(session)  # should not raise
