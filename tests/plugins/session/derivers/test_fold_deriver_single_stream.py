"""ADR-0191 Wave D: StepTreeFoldDeriver single-stream SSOT tests."""

from __future__ import annotations

from pathlib import Path

from lca.plugins.session.derivers.step_tree.fold_deriver import StepTreeFoldDeriver
from lca.session.append import Session


def test_iter_events_session_only_when_snapshot_nonempty(tmp_path: Path) -> None:
    session = Session("single_stream_1")
    session.append("turn.started.v1", {"turn": 1})
    spine_path = tmp_path / "single_stream_1.spine.jsonl"
    spine_path.write_text(
        '{"type":"spine.orphan","seq":99,"time":1,"data":{}}\n',
        encoding="utf-8",
    )
    deriver = StepTreeFoldDeriver(
        run_id="single_stream_1",
        run_dir=tmp_path,
        session=session,
        spine_path=spine_path,
    )
    events = list(deriver._iter_events())
    assert len(events) == 1
    assert events[0].type == "turn.started.v1"


def test_iter_events_spine_only_when_session_empty(tmp_path: Path) -> None:
    spine_path = tmp_path / "cold.spine.jsonl"
    spine_path.write_text(
        '{"type":"phase.think.fold","seq":0,"time":1,"data":{"phase":"think"}}\n',
        encoding="utf-8",
    )
    deriver = StepTreeFoldDeriver(
        run_id="cold",
        run_dir=tmp_path,
        session=None,
        spine_path=spine_path,
    )
    events = list(deriver._iter_events())
    assert len(events) == 1
    assert events[0]["type"] == "phase.think.fold"
