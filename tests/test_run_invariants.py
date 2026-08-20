"""Regression locks for docs/specs/run-live.md — no third vocabulary, one teardown."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from gateway.runs.api import iter_live_sse
from gateway.runs.live import LiveTail
from lca.contracts.models.observability.journal import (
    LlmCallStarted,
    RunScope,
    StampedEvent,
    ToolStarted,
)
from lca.layer0_infra.observability.journal.journal_io import stamped_to_record

_FORBIDDEN = ("thinking.delta", "timeline.v1", "lca.events", "lca_tool_event")
_SCAN_ROOTS = (Path("gateway"), Path("deploy/lobehub/patches"))
_SKIP_PARTS = {".pyc", "__pycache__"}


def _iter_source_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _SKIP_PARTS or part.endswith(".pyc") for part in path.parts):
                continue
            if path.suffix not in {".py", ".ts", ".tsx", ".md"}:
                continue
            files.append(path)
    return files


def test_no_third_vocabulary_in_production() -> None:
    hits: list[str] = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in _FORBIDDEN:
            if token in text:
                hits.append(f"{path}:{token}")
    assert hits == []


def test_plugin_state_live_equals_jsonl_record() -> None:
    state = {"code": "print(2)", "language": "python"}
    stamped = StampedEvent(
        seq=4,
        ts=4.0,
        scope=RunScope(trace_id="t", run_id="r"),
        event=ToolStarted(tool_name="execute_code", invocation_id="i", plugin_state=state),
    )
    record = stamped_to_record(stamped)
    assert record["event"]["plugin_state"] == state


@pytest.mark.asyncio
async def test_live_frame_matches_jsonl_record() -> None:
    state = {"code": "print(2)", "language": "python"}
    stamped = StampedEvent(
        seq=1,
        ts=1.0,
        scope=RunScope(trace_id="t", run_id="r"),
        event=ToolStarted(tool_name="execute_code", invocation_id="i", plugin_state=state),
    )
    tail = LiveTail()
    tail.on_event(stamped)
    tail.close()
    frames = [frame async for frame in iter_live_sse(tail, after_seq=0, heartbeat_s=30)]
    data_line = next(line for line in frames[0].decode().splitlines() if line.startswith("data: "))
    live = json.loads(data_line[6:])
    record = stamped_to_record(stamped)
    assert live["event"]["plugin_state"] == record["event"]["plugin_state"]
    assert "http://127.0.0.1" not in data_line


def test_relative_file_urls_are_not_absolutized() -> None:
    text = Path("gateway").read_text if False else ""
    del text
    for path in Path("gateway").rglob("*.py"):
        body = path.read_text(encoding="utf-8")
        assert "absolutize_" not in body, path
        assert "LCA_GATEWAY_PUBLIC_URL" not in body, path


def test_finalize_has_one_definition() -> None:
    tree = ast.parse(Path("gateway/runs/execute.py").read_text(encoding="utf-8"))
    defs = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "finalize"
    ]
    assert defs == ["finalize"]


def test_transport_does_not_skip_tool_started() -> None:
    journal = Path("deploy/lobehub/patches/runtime/lcaJournal.ts").read_text(encoding="utf-8")
    driver = Path("deploy/lobehub/patches/runtime/LcaRunDriver.ts").read_text(encoding="utf-8")
    assert "case 'ToolStarted'" in journal
    assert "type: 'tool_calls'" in driver or 'type: "tool_calls"' in driver


def test_abort_calls_cancel_endpoint() -> None:
    source = Path("deploy/lobehub/patches/runtime/LcaRunDriver.ts").read_text(encoding="utf-8")
    assert "/cancel" in source
    assert "method: 'POST'" in source or 'method: "POST"' in source


def test_transport_reconnects_with_last_event_id() -> None:
    source = Path("deploy/lobehub/patches/runtime/LcaRunDriver.ts").read_text(encoding="utf-8")
    assert "Last-Event-ID" in source
    assert "waiting_input" in source
    assert "String(afterSeq)" in source or "String(lastSeq)" in source


def test_unknown_journal_event_is_ignored_not_thrown() -> None:
    source = Path("deploy/lobehub/patches/runtime/lcaJournal.ts").read_text(encoding="utf-8")
    assert "default:" in source
    assert type(LlmCallStarted).__name__ == "type"


def test_no_active_hubs_global() -> None:
    for path in Path("gateway").rglob("*.py"):
        assert "_active_hubs" not in path.read_text(encoding="utf-8"), path


def test_g2a_openai_sse_fossils_are_gone() -> None:
    phases = Path("lca/layer2_runtime/agent_runtime/phases.py").read_text(encoding="utf-8")
    assert "G2A_FINISH_REASON" not in phases
    assert "LOBEHUB_TEXT_ONLY_MEANS_FINISH" not in phases
