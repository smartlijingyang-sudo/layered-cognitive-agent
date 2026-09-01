"""doctor.v3 predicates — broken_hop is the first false hop."""

from __future__ import annotations

import json
from pathlib import Path

from lca.infrastructure.observability.journal.engine.journal_io import JOURNAL_SCHEMA_VERSION
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.plugins.transport.webserver.handlers.runs.doctor import diagnose
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession, RunStatus


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _row(seq: int, event_type: str, event: dict) -> dict:
    return {
        "schema": JOURNAL_SCHEMA_VERSION,
        "seq": seq,
        "ts": float(seq),
        "scope": {"trace_id": "t", "run_id": "run_x"},
        "event_type": event_type,
        "event": event,
    }


def _session(*, status: RunStatus, tail: LiveTail, jsonl_path: Path) -> RunSession:
    return RunSession(
        run_id="run_x",
        trace_id="t",
        jsonl_path=jsonl_path,
        tail=tail,
        question="q",
        user_text="q",
        mode="solo",
        status=status,
    )


def test_doctor_flags_h3_when_tail_closes_while_running(tmp_path: Path) -> None:
    path = tmp_path / "run_x.jsonl"
    _write_jsonl(
        path,
        [
            _row(1, "AgentRunStarted", {"agent_role": "助手", "objective": "q"}),
            _row(2, "ReasoningDelta", {"step": 0, "text_delta": "x", "seq": 0}),
        ],
    )
    tail = LiveTail()
    session = _session(status=RunStatus.RUNNING, tail=tail, jsonl_path=path)
    tail.close()
    report = diagnose(session, path)
    assert report.schema == "doctor.v3"
    assert report.broken_hop == "H3"
    assert report.hops["H3"].ok is False


def test_doctor_factory_unverifiable_from_jsonl(tmp_path: Path) -> None:
    """ADR-0102: the renderer-facing projection lives on ToolInvoked.

    ``projected_state`` is SSE-only — jsonl never carries it (stripped by
    ``JsonlJournalProjector._strip_sse_only_fields`` before disk write).
    Therefore the doctor cannot fact-check the projection from jsonl; the
    factory field is always ok=True / missing list empty when scanning the
    journal.  Wire-level validation lives in the SSE encoder / contract
    registry, not here.
    """
    path = tmp_path / "run_x.jsonl"
    _write_jsonl(
        path,
        [
            _row(1, "AgentRunStarted", {"agent_role": "助手", "objective": "q"}),
            _row(2, "ToolStarted", {"tool_name": "web_search", "invocation_id": "inv1"}),
            _row(
                3,
                "ToolInvoked",
                {"tool_name": "web_search", "invocation_id": "inv1", "ok": True},
            ),
            _row(4, "AgentRunFinished", {"status": "completed", "output_text": "done"}),
        ],
    )
    tail = LiveTail()
    session = _session(status=RunStatus.COMPLETED, tail=tail, jsonl_path=path)
    report = diagnose(session, path)
    assert report.factory["ok"] is True
    assert list(report.factory["tools_missing_plugin_state"]) == []
    assert report.broken_hop is None


def test_doctor_broken_hop_is_first_false(tmp_path: Path) -> None:
    path = tmp_path / "run_x.jsonl"
    _write_jsonl(path, [])
    tail = LiveTail()
    tail.close()
    session = _session(status=RunStatus.RUNNING, tail=tail, jsonl_path=path)
    report = diagnose(session, path)
    assert report.hops["H2"].ok is False
    assert report.hops["H3"].ok is False
    assert report.broken_hop == "H2"


def test_doctor_reads_v2_envelope_fields(tmp_path: Path) -> None:
    path = tmp_path / "run_x.jsonl"
    _write_jsonl(
        path,
        [
            {
                "schema": JOURNAL_SCHEMA_VERSION,
                "event_id": "evt-finished",
                "run_id": "run_x",
                "run_seq": 4,
                "occurred_at": 4.0,
                "committed_at": 4.0,
                "scope": {"trace_id": "t", "run_id": "run_x", "agent_role": "助手", "step": 0},
                "causation": {"parent_event_id": "", "links": []},
                "descriptor": {
                    "type": "AgentRunFinished",
                    "version": 1,
                    "payload_schema_version": 1,
                },
                "data": {"status": "completed", "output_text": "done", "error": ""},
                "evidence": [],
            }
        ],
    )
    session = _session(status=RunStatus.COMPLETED, tail=LiveTail(), jsonl_path=path)

    report = diagnose(session, path)

    assert report.hops["H2"].ok is True
    assert report.hops["H2"].extra["last_seq"] == 4
    assert report.hops["H2"].extra["counts"] == {"AgentRunFinished": 1}


def test_doctor_works_from_jsonl_without_session(tmp_path: Path) -> None:
    path = tmp_path / "run_x.jsonl"
    _write_jsonl(
        path,
        [
            _row(1, "AgentRunStarted", {"agent_role": "助手", "objective": "q"}),
            _row(2, "AgentRunFinished", {"status": "completed"}),
        ],
    )
    report = diagnose(None, path)
    assert report.hops["H1"].ok is True
    assert report.hops["H2"].ok is True
    assert report.hops["H3"].ok is None
    assert report.hops["H4"].ok is None
    assert report.hops["H5"].ok is None
    assert report.broken_hop is None
