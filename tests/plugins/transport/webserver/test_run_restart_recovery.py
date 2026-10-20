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

import pytest

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
    session.loaded_namespaces = frozenset({"shell", "file"})

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
    assert bundle["loaded_namespaces"] == ["file", "shell"]

    loaded = load_resume_bundle("run-rec-1", session.locator)
    assert loaded == bundle


def test_load_resume_bundle_missing_returns_none(tmp_path: Path) -> None:
    locator = MagicMock(name="locator")
    locator.run_dir.return_value = tmp_path / "nope"
    assert load_resume_bundle("run-missing", locator) is None


@pytest.mark.parametrize(
    "payload",
    [
        # bad approval_request type
        '{"run_id": "run-corrupt", "approval_request": "not-a-dict"}',
        # missing approval_id
        '{"run_id": "run-corrupt", "approval_request": {"type": "ask_user_question"}}',
        # empty approval_id
        '{"run_id": "run-corrupt", "approval_request": {"approval_id": ""}, "resume_point": {"step": 0}}',
        # non-dict JSON
        "[1, 2, 3]",
        # missing resume_point (valid approval side, nothing to resume)
        '{"run_id": "run-corrupt", "approval_request": {"approval_id": "a:1"}}',
        # unparseable resume_point (deserialize_resume_point fails closed)
        '{"run_id": "run-corrupt", "approval_request": {"approval_id": "a:1"}, "resume_point": {"step": -1}}',
        # invalid JSON text
        "not json at all{{{",
    ],
)
def test_load_resume_bundle_corrupt_returns_none(tmp_path: Path, payload: str) -> None:
    run_dir = tmp_path / "traces" / "run-corrupt"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "resume_bundle.json").write_text(payload, encoding="utf-8")
    locator = MagicMock(name="locator")
    locator.run_dir.return_value = run_dir
    assert load_resume_bundle("run-corrupt", locator) is None


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
    session.locator.run_dir.return_value = run_dir
    write_resume_bundle(session)
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


def test_ra161_validate_bundle_rejects_mistyped_loaded_namespaces(tmp_path: Path) -> None:
    """RA-161: loaded_namespaces 键曾绕过 load contract —— 错类型必须判 corrupt。

    裸字符串会在 _restore_from_bundle 里静默变成 frozenset("shell") 的字符集；
    缺键（2026-10-19 前的老 bundle）仍允许，下游 or () 兜底。
    """
    from lca.plugins.transport.webserver.carrier.runs.recovery import validate_bundle

    run_dir = tmp_path / "traces" / "run-rec-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    session = _paused_session()
    session.locator.run_dir.return_value = run_dir
    session.loaded_namespaces = frozenset({"shell"})
    write_resume_bundle(session)
    bundle = json.loads((run_dir / "resume_bundle.json").read_text(encoding="utf-8"))

    # writer 产出的合法形态（list[str]）通过
    assert validate_bundle(bundle, "run-rec-1") == bundle
    # 缺键（老 bundle）仍通过
    no_key = dict(bundle)
    del no_key["loaded_namespaces"]
    assert validate_bundle(no_key, "run-rec-1") == no_key
    # 错类型一律判 corrupt
    for bad in ("shell", {"shell": True}, [1, 2], [["shell"]], [None]):
        mutated = dict(bundle)
        mutated["loaded_namespaces"] = bad
        assert validate_bundle(mutated, "run-rec-1") is None


def test_ra173_bundle_field_inventory_round_trip(tmp_path: Path) -> None:
    """RA-173: write -> read round-trips every inventoried field.

    The inventory (_BUNDLE_FIELDS) is the single list both the writer and
    the reader walk; a field added on write but forgotten on read would
    surface here as a key the bundle has but the read seam drops.
    """
    from lca.plugins.transport.webserver.carrier.runs.recovery import _BUNDLE_FIELDS

    run_dir = tmp_path / "traces" / "run-ra173"
    run_dir.mkdir(parents=True, exist_ok=True)
    session = _paused_session(run_id="run-ra173")
    session.locator.run_dir.return_value = run_dir
    # Non-default values on every inventoried field so the round-trip is real.
    session.trace_id = "trace-ra173"
    session.question = "海还是山？"
    session.user_text = "只问一题，别啰嗦。"
    session.mode = "team"
    session.plan_ref = "plan-ra173"
    session.agent = AgentRef(agent_id="asst_1", name="副驾")
    session.device_id = "dev-1"
    session.plane = "web"
    session.extra_plane = "extra"
    session.execution_target = "local"
    session.assistant_id = "asst_x"
    session.user_id = "u9"
    session.topic_id = "tpc-9"
    session.origin = "handoff"
    session.developer_seed = "seed"
    session.developer_seed_job_id = "job-1"
    session.attachment_ids = ("att-1", "att-2")
    session.started_at = 4242.5
    session.loaded_namespaces = frozenset({"shell"})

    write_resume_bundle(session)
    bundle = json.loads((run_dir / "resume_bundle.json").read_text(encoding="utf-8"))

    expected = {
        "trace_id": "trace-ra173",
        "question": "海还是山？",
        "user_text": "只问一题，别啰嗦。",
        "mode": "team",
        "plan_ref": "plan-ra173",
        "agent_id": "asst_1",
        "agent_name": "副驾",
        "device_id": "dev-1",
        "plane": "web",
        "extra_plane": "extra",
        "execution_target": "local",
        "assistant_id": "asst_x",
        "user_id": "u9",
        "topic_id": "tpc-9",
        "origin": "handoff",
        "developer_seed": "seed",
        "developer_seed_job_id": "job-1",
        "attachment_ids": ("att-1", "att-2"),
        "started_at": 4242.5,
        "loaded_namespaces": frozenset({"shell"}),
    }
    restored = {f.name: f.read(bundle) for f in _BUNDLE_FIELDS}
    # Dict equality pins both directions: no inventoried field may be
    # missing from the bundle, and no extra field may sneak in untested.
    assert restored == expected


def test_ra173_validate_bundle_rejects_missing_required_field(tmp_path: Path) -> None:
    """RA-173: a bundle missing a required inventoried field is rejected.

    Before RA-173 a bundle without 'question' passed validation and rebuilt
    a zombie session with an empty ask card; optional fields keep their
    documented defaults and still load when absent.
    """
    from lca.plugins.transport.webserver.carrier.runs.recovery import (
        _BUNDLE_FIELDS,
        validate_bundle,
    )

    run_dir = tmp_path / "traces" / "run-ra173-req"
    run_dir.mkdir(parents=True, exist_ok=True)
    session = _paused_session(run_id="run-ra173-req")
    session.locator.run_dir.return_value = run_dir
    write_resume_bundle(session)
    bundle = json.loads((run_dir / "resume_bundle.json").read_text(encoding="utf-8"))

    required = [f.name for f in _BUNDLE_FIELDS if f.required]
    assert required, "the inventory must own at least one required field"
    for name in required:
        deleted = dict(bundle)
        del deleted[name]
        assert validate_bundle(deleted, "run-ra173-req") is None
        nulled = dict(bundle)
        nulled[name] = None
        assert validate_bundle(nulled, "run-ra173-req") is None

    optional = next(f.name for f in _BUNDLE_FIELDS if not f.required)
    dropped = dict(bundle)
    del dropped[optional]
    assert validate_bundle(dropped, "run-ra173-req") == dropped
