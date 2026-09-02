"""doctor.v3 predicates for the spine-fallback path.

Legacy ``diagnose_legacy``(7 个 v2 hop)已下线:doctor 现在分两步 —
``journal.json`` 存在 → ``diagnose_step_tree``(完整 8 hop),否则 spine SSOT
``events.jsonl`` 兜底 → 最小 H1 报告(只声明 step-tree materialization 缺失)。

本测试覆盖 spine fallback 的 spec:
  - broken_hop 始终是 H1(journal.json 缺失即 H1=False)
  - H2/H3/H4/H5/H6/H7 在 spine fallback 下统一 not evaluated(None)
  - 接受 session=None + 仅有 events.jsonl 的诊断
"""

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


def _session(*, status: RunStatus, tail: LiveTail, spine_path: Path) -> RunSession:
    return RunSession(
        run_id="run_x",
        trace_id="t",
        spine_path=spine_path,
        tail=tail,
        question="q",
        user_text="q",
        mode="solo",
        status=status,
    )


def test_spine_fallback_flags_h1_when_step_tree_missing(tmp_path: Path) -> None:
    """spine events.jsonl 存在但 step-tree journal.json 缺失 → H1=False。"""
    path = tmp_path / "run_x.jsonl"
    _write_jsonl(
        path,
        [
            _row(1, "AgentRunStarted", {"agent_role": "助手", "objective": "q"}),
            _row(2, "ReasoningDelta", {"step": 0, "text_delta": "x", "seq": 0}),
        ],
    )
    tail = LiveTail()
    tail.close()
    session = _session(status=RunStatus.RUNNING, tail=tail, spine_path=path)
    report = diagnose(session, path)
    assert report.schema == "doctor.v3"
    assert report.broken_hop == "H1"
    assert report.hops["H1"].ok is False


def test_spine_fallback_factory_ok(tmp_path: Path) -> None:
    """spine fallback path 不解析 tool/plugin state,factory 永远 ok=True / 空列表。"""
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
    session = _session(status=RunStatus.COMPLETED, tail=tail, spine_path=path)
    report = diagnose(session, path)
    assert report.factory["ok"] is True
    assert list(report.factory["tools_missing_plugin_state"]) == []


def test_spine_fallback_broken_hop_is_first_false(tmp_path: Path) -> None:
    """通用 spec:broken_hop 是第一个 ok=False 的 hop;fallback path 下固定为 H1。"""
    path = tmp_path / "run_x.jsonl"
    _write_jsonl(path, [])
    tail = LiveTail()
    tail.close()
    session = _session(status=RunStatus.RUNNING, tail=tail, spine_path=path)
    report = diagnose(session, path)
    assert report.hops["H1"].ok is False
    assert report.broken_hop == "H1"


def test_spine_fallback_unevaluated_hops_are_none(tmp_path: Path) -> None:
    """spine fallback 下 H2-H7 一律 not evaluated(None),不假装能做诊断。"""
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
    session = _session(status=RunStatus.COMPLETED, tail=LiveTail(), spine_path=path)
    report = diagnose(session, path)
    for hop in ("H2", "H3", "H4", "H5", "H6", "H7"):
        assert report.hops[hop].ok is None, f"{hop} should be not evaluated in fallback"


def test_spine_fallback_works_without_session(tmp_path: Path) -> None:
    """doctor 接受 None session + 仅有 events.jsonl(spine SSOT) 路径。"""
    path = tmp_path / "run_x.jsonl"
    _write_jsonl(
        path,
        [
            _row(1, "AgentRunStarted", {"agent_role": "助手", "objective": "q"}),
            _row(2, "AgentRunFinished", {"status": "completed"}),
        ],
    )
    report = diagnose(None, path)
    assert report.broken_hop == "H1"
    assert report.hops["H1"].ok is False
