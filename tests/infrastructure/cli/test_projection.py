"""Tests for the shared CLI projection utilities.

Pins the contract used by debug-graph, journal/replay, and future CLI
projection code: spine parsing, domain filtering, and output summarization.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.infrastructure.cli.commands._shared.projection import (
    filter_by_domain,
    load_spine_events,
    spine_filename_for_run_cwd,
    summarize_outputs,
    truncate,
)


def _valid_event(seq: int, ep: str, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "execution_point": ep,
        "channel": "fact",
        "span_id": f"span_{seq}",
        "parent_span_id": None,
        "sequence": seq,
        "epoch": 1,
        "causality_id": f"cause_{seq}",
        "outcome": None,
        "when": "2026-09-14T00:00:00+00:00",
        "when_corrected": "2026-09-14T00:00:00+00:00",
        "prev_event_hash": None,
        "run_id": "run_unit",
        "step_id": None,
        "payload": {},
        "phase": "live",
        "reason": None,
        "trace_id": None,
    }
    base.update(extra)
    return base


@pytest.fixture
def run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    rd = tmp_path / "traces" / "runs" / "run_unit"
    rd.mkdir(parents=True)
    spine = rd / "run_unit.spine.jsonl"
    spine.write_text(
        "\n".join(
            json.dumps(e)
            for e in [
                _valid_event(1, "phase_graph.node.start"),
                _valid_event(2, "phase_graph.node.end"),
                _valid_event(3, "llm.call.end"),
                _valid_event(4, "body.tool.execute.start"),
                _valid_event(5, "kernel.run.stop"),
                # malformed line — must be skipped
                "{this is not json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rd


def test_load_spine_events_returns_records(run_dir: Path) -> None:
    events = load_spine_events("run_unit")
    assert len(events) == 5
    assert [e["execution_point"] for e in events] == [
        "phase_graph.node.start",
        "phase_graph.node.end",
        "llm.call.end",
        "body.tool.execute.start",
        "kernel.run.stop",
    ]


def test_load_spine_events_missing_returns_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_spine_events("does_not_exist") == []


def test_load_spine_events_honors_traces_root(run_dir: Path) -> None:
    # Point at a non-existent root: must return [], not raise.
    assert load_spine_events("run_unit", traces_root=Path("/nope")) == []


def test_filter_by_domain_llm_and_tool(run_dir: Path) -> None:
    events = load_spine_events("run_unit")
    llm = filter_by_domain(events, "llm")
    tool = filter_by_domain(events, "tool")
    assert [e["execution_point"] for e in llm] == ["llm.call.end"]
    assert [e["execution_point"] for e in tool] == ["body.tool.execute.start"]


def test_filter_by_domain_unknown_returns_empty(run_dir: Path) -> None:
    assert filter_by_domain(load_spine_events("run_unit"), "nope") == []


def test_truncate_short_passthrough() -> None:
    assert truncate("hello", 120) == "hello"


def test_truncate_long_adds_ellipsis() -> None:
    assert truncate("a" * 200, 50).endswith("...")


def test_summarize_outputs_dict_nested_and_list() -> None:
    lines = summarize_outputs(
        {
            "manifest": {"digest": "sha256:abc", "items": []},
            "items": [1, 2, 3],
            "text": "hello",
        }
    )
    assert any("manifest" in line and "digest=" in line for line in lines)
    assert any("items = list[3]" in line for line in lines)
    assert any("text = 'hello'" in line for line in lines)


def test_spine_filename_for_run_cwd_resolves_under_traces() -> None:
    p = spine_filename_for_run_cwd("run_unit")
    assert p == Path("traces/runs/run_unit/run_unit.spine.jsonl")
