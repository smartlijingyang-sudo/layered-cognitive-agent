"""Tests for the waterfall deriver's tolerant input handling.

Real spine rows no longer satisfy the strict EventRecord dataclass
(sequence / span_id / when / epoch / causality_id are absent; category
/ event_hash / trace_id are present). The deriver must accept dict
shaped rows directly so ``lca-ops journal trajectory`` produces
non-empty HTML on real runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.infrastructure.observability.spine.derivers.waterfall.waterfall import (
    WaterfallDeriver,
)


@pytest.fixture
def real_run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    run_id = "run_test_waterfall"
    rd = tmp_path / "traces" / "runs" / run_id
    rd.mkdir(parents=True)
    rows = [
        {"execution_point": "kernel.run.start", "channel": "fact",
         "ts": "2026-09-14T00:00:00+00:00", "payload": {}},
        {"execution_point": "llm.call.start", "channel": "control",
         "ts": "2026-09-14T00:00:01+00:00", "step_id": "step-001",
         "payload": {"model": "qwen3.7-plus"}},
        {"execution_point": "llm.call.end", "channel": "control",
         "ts": "2026-09-14T00:00:02+00:00",
         "payload": {"model": "qwen3.7-plus", "latency_ms": 800,
                     "outcome": "success"}},
        {"execution_point": "phase_graph.node.end", "channel": "control",
         "ts": "2026-09-14T00:00:03+00:00",
         "payload": {"node_id": "think.reason", "outcome": "failure"}},
        {"execution_point": "kernel.run.stop", "channel": "fact",
         "ts": "2026-09-14T00:00:04+00:00",
         "payload": {"outcome": "failure"}},
    ]
    (rd / f"{run_id}.spine.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    return rd


def test_waterfall_accepts_dict_rows_directly(real_run_dir: Path) -> None:
    """The CLI feeds SpineRow dicts straight into on_event; the deriver
    must not require EventRecord construction.
    """
    from lca.infrastructure.cli.commands._shared.projection import (
        load_spine_events,
    )

    deriver = WaterfallDeriver("run_test_waterfall")
    for row in load_spine_events("run_test_waterfall"):
        deriver.on_event(row)

    html = deriver.render()
    assert "(no events)" not in html, "deriver dropped real spine rows"
    assert "kernel.run.start" in html
    assert "llm.call.end" in html
    assert "think.reason" in html
    assert "kernel.run.stop" in html


def test_waterfall_failure_outcome_marked_fail(real_run_dir: Path) -> None:
    from lca.infrastructure.cli.commands._shared.projection import (
        load_spine_events,
    )

    deriver = WaterfallDeriver("run_test_waterfall")
    for row in load_spine_events("run_test_waterfall"):
        deriver.on_event(row)
    html = deriver.render()
    assert 'class="fail"' in html, "kernel.run.stop=failure must colour red"
    assert 'class="ok"' in html, "llm.call.end=success must colour green"


def test_waterfall_glyph_mapping(real_run_dir: Path) -> None:
    from lca.infrastructure.cli.commands._shared.projection import (
        load_spine_events,
    )

    deriver = WaterfallDeriver("run_test_waterfall")
    for row in load_spine_events("run_test_waterfall"):
        deriver.on_event(row)
    html = deriver.render()
    assert "▶" in html, "kernel.run.start must use the start glyph"
    assert "🧠" in html, "llm.call.* must use the LLM glyph"
    assert "■" in html, "kernel.run.stop must use the stop glyph"


def test_waterfall_rows_sorted_by_ts() -> None:
    """When sequence is missing (real spine), rows must fall back to ts."""
    deriver = WaterfallDeriver("run_x")
    # inject out of order to make sure the sort actually happens
    deriver.on_event({"execution_point": "phase_graph.node.end",
                      "ts": "2026-09-14T00:00:05+00:00",
                      "payload": {"outcome": "failure", "node_id": "later"}})
    deriver.on_event({"execution_point": "kernel.run.start",
                      "ts": "2026-09-14T00:00:00+00:00",
                      "payload": {}})
    deriver.on_event({"execution_point": "llm.call.end",
                      "ts": "2026-09-14T00:00:03+00:00",
                      "payload": {"model": "m", "outcome": "success"}})
    html = deriver.render()
    # ts order in the rendered body: start, llm, later
    idx_start = html.index("kernel.run.start")
    idx_llm = html.index("llm.call.end")
    idx_later = html.index('class="fail"')
    assert idx_start < idx_llm < idx_later, "rows must be ts-sorted"


def test_waterfall_drops_rows_without_execution_point() -> None:
    deriver = WaterfallDeriver("run_x")
    deriver.on_event({"payload": {}})  # no execution_point
    deriver.on_event({"execution_point": "kernel.run.start",
                      "ts": "2026-09-14T00:00:00+00:00", "payload": {}})
    html = deriver.render()
    assert "kernel.run.start" in html
    assert "(no events)" not in html
