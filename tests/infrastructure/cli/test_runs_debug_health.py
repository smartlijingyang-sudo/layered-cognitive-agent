"""``lca-ops runs debug`` rewrite tests for ``RunHealthReport`` (PR-1 / Task 1.6).

Per spec
``docs/superpowers/specs/2026-09-16-run-health-and-execution-closure-design.md``
§2.4 (debug 5 layers): the five debug layers
``summary / graph / events / diff / explain`` MUST read
``RunHealthReport`` from ``fold_run_health`` instead of inspecting raw
``phase_graph.node.end.outcome`` and ``kernel.run.stop.outcome``.

These tests pin the new behaviour:
1. Each layer's ``anomalies_present`` / ``root_cause_present`` flag is
   driven by ``report.summary.conditions_failed`` (and not by ad-hoc
   per-layer judgement of raw spine events).
2. The ``next_layer_hint`` (``hint``) of every layer points to
   ``health`` (or ``explain``) when ``conditions_failed > 0``.
3. ``_layer_explain``'s ``root_cause_kind`` becomes
   ``health_conditions_failed`` when the report flags failed conditions.
4. The 3 audit runs (``run_3383288d63e7``, ``run_3cf6e7c036b3``,
   ``run_feb0f21ee770``) keep their previous verdict:
   ``root_cause_present=False`` for the two healthy runs and
   ``root_cause_present=True`` for the B-1 poisoned run
   (which the existing ``LlmDeriver`` flags as ``llm.status=failed``).

Test fixture data:
- We write synthetic spines with TOP-LEVEL ``run_id`` (matching the
  current ``_read_spine_events`` parser in
  ``lca/plugins/observability/health/run_health_fold.py``). The real
  audit-run spine format places ``run_id`` under ``payload`` (a
  pre-existing Task 1.4 parser quirk) — out of scope here; the
  synthetic spines reliably drive the derivers to the same verdicts
  the brief documents for the audit runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lca.infrastructure.cli.cli.cli import app

# ── helpers ─────────────────────────────────────────────────────────


def _spine_for(run_id: str, *, llm_tool_messages_missing: bool) -> list[dict]:
    """Synthesize a spine that drives the LlmDeriver to either ok or failed.

    Mirrors the audit-run shape (kernel.run.start, llm.request.header,
    llm.call.end, step.tool_call.record, step.tool_result.record,
    phase_graph.node.{start,end}, kernel.run.stop) but with TOP-LEVEL
    ``run_id`` so the existing fold parser yields a non-empty
    ``conditions`` list.

    The first ``llm.request.header`` carries an ``assistant`` message
    with ``tool_calls=[{id: "tc1"}]``. The healthy run's SECOND
    ``llm.request.header`` echoes ``role=tool`` for ``tc1`` (B-1
    closed); the B-1 poisoned run's second header DROPS the tool
    response, so the LlmDeriver flags ``llm.status=failed``.
    """
    base: list[dict] = [
        {"event_id": f"{run_id}:1", "ts": "2026-09-16T02:00:00+00:00",
         "run_id": run_id, "execution_point": "kernel.run.start",
         "payload": {"run_id": run_id}},
        {"event_id": f"{run_id}:2", "ts": "2026-09-16T02:00:01+00:00",
         "run_id": run_id, "execution_point": "phase.perceive.fold",
         "payload": {"run_id": run_id}},
        {"event_id": f"{run_id}:3", "ts": "2026-09-16T02:00:02+00:00",
         "run_id": run_id, "execution_point": "phase.think.fold",
         "payload": {"run_id": run_id}},
        {"event_id": f"{run_id}:4", "ts": "2026-09-16T02:00:03+00:00",
         "run_id": run_id, "execution_point": "llm.request.header",
         "payload": {"run_id": run_id,
                     "messages": [{"role": "user", "content": "hi"}],
                     "tools": [], "step_id": "s1"}},
        {"event_id": f"{run_id}:5", "ts": "2026-09-16T02:00:04+00:00",
         "run_id": run_id, "execution_point": "llm.call.end",
         "payload": {"run_id": run_id, "outcome": "success", "model": "x"}},
        {"event_id": f"{run_id}:6", "ts": "2026-09-16T02:00:05+00:00",
         "run_id": run_id, "execution_point": "llm.request.header",
         "payload": {"run_id": run_id,
                     "messages": [
                         {"role": "assistant", "content": "",
                          "tool_calls": [{"id": "tc1", "type": "function",
                                          "function": {"name": "x",
                                                       "arguments": "{}"}}]},
                     ],
                     "tools": [], "step_id": "s2"}},
        {"event_id": f"{run_id}:7", "ts": "2026-09-16T02:00:06+00:00",
         "run_id": run_id, "execution_point": "step.tool_call.record",
         "payload": {"run_id": run_id, "tool_call": {"id": "tc1"}}},
        {"event_id": f"{run_id}:8", "ts": "2026-09-16T02:00:07+00:00",
         "run_id": run_id, "execution_point": "step.tool_result.record",
         "payload": {"run_id": run_id, "tool_call_id": "tc1", "ok": True}},
        {"event_id": f"{run_id}:9", "ts": "2026-09-16T02:00:08+00:00",
         "run_id": run_id, "execution_point": "llm.request.header",
         "payload": {"run_id": run_id,
                     "messages": [
                         {"role": "tool", "content": "ok",
                          "tool_call_id": "tc1"},
                         {"role": "user", "content": "follow-up"},
                     ],
                     "tools": [], "step_id": "s3"}},
        {"event_id": f"{run_id}:10", "ts": "2026-09-16T02:00:09+00:00",
         "run_id": run_id, "execution_point": "llm.call.end",
         "payload": {"run_id": run_id, "outcome": "success", "model": "x"}},
        {"event_id": f"{run_id}:11", "ts": "2026-09-16T02:00:10+00:00",
         "run_id": run_id, "execution_point": "phase.act.fold",
         "payload": {"run_id": run_id}},
        {"event_id": f"{run_id}:12", "ts": "2026-09-16T02:00:11+00:00",
         "run_id": run_id, "execution_point": "kernel.run.stop",
         "payload": {"run_id": run_id, "outcome": "success"}},
    ]
    if llm_tool_messages_missing:
        # Drop the role=tool message in the 3rd header so the LlmDeriver's
        # "tool_call ids never matched in any header" rule fires (spec §4
        # LlmDeriver). Drop the tool_result.record too so ToolDeriver stays
        # happy (we want llm=failed, not tool=failed).
        base = [e for e in base
                if not (e.get("execution_point") == "llm.request.header"
                        and any(m.get("role") == "tool"
                                 for m in (e.get("payload") or {}).get("messages") or []))]
        base = [e for e in base
                if e.get("execution_point") != "step.tool_result.record"]
    return base


def _write_spine(tmp_path: Path, run_id: str) -> Path:
    run_dir = tmp_path / "traces" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    spine_path = run_dir / f"{run_id}.spine.jsonl"
    spine_path.write_text(
        "\n".join(json.dumps(e) for e in _spine_for(run_id, llm_tool_messages_missing=False)) + "\n",
        encoding="utf-8",
    )
    return spine_path


def _write_b1_spine(tmp_path: Path, run_id: str) -> Path:
    """B-1 poisoned run: tool_call.record with NO matching tool result."""
    run_dir = tmp_path / "traces" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    spine_path = run_dir / f"{run_id}.spine.jsonl"
    spine_path.write_text(
        "\n".join(json.dumps(e) for e in _spine_for(run_id, llm_tool_messages_missing=True)) + "\n",
        encoding="utf-8",
    )
    return spine_path


def _invoke(layer: str, run_id: str) -> dict:
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "debug", run_id, "--layer", layer, "--output", "json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


# ── 5 layer tests (one per layer) ──────────────────────────────────


def test_layer_summary_reads_health_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``_layer_summary`` returns ``anomalies_present=True`` for B-1 runs."""
    monkeypatch.chdir(tmp_path)
    run_id = "run_feb0f21ee770"
    _write_b1_spine(tmp_path, run_id)
    payload = _invoke("summary", run_id)
    assert payload["layer"] == "summary"
    assert payload["anomalies_present"] is True
    # Health-driven hint points to explain
    assert "health" in payload["hint"] or "explain" in payload["hint"]


def test_layer_graph_reads_health_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``_layer_graph`` reflects ``report.summary.conditions_failed > 0``."""
    monkeypatch.chdir(tmp_path)
    run_id = "run_feb0f21ee770"
    _write_b1_spine(tmp_path, run_id)
    payload = _invoke("graph", run_id)
    assert payload["layer"] == "graph"
    # health_summary surfaces the failure (via the report's by_type)
    assert payload.get("anomalies_present") is True
    assert "health" in payload["hint"] or "explain" in payload["hint"]


def test_layer_events_includes_health_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``_layer_events`` adds a ``health_summary`` field from the report."""
    monkeypatch.chdir(tmp_path)
    run_id = "run_feb0f21ee770"
    _write_b1_spine(tmp_path, run_id)
    payload = _invoke("events", run_id)
    assert payload["layer"] == "events"
    assert "health_summary" in payload
    assert "by_type" in payload["health_summary"]
    # B-1 poisoned run: llm status failed
    assert payload["health_summary"]["by_type"].get("llm") == "failed"


def test_layer_diff_includes_health_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``_layer_diff`` reads from health (not from raw blueprint diff)."""
    monkeypatch.chdir(tmp_path)
    run_id = "run_feb0f21ee770"
    _write_b1_spine(tmp_path, run_id)
    payload = _invoke("diff", run_id)
    assert payload["layer"] == "diff"
    assert "health_summary" in payload


def test_layer_explain_root_cause_from_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``_layer_explain`` flips ``root_cause_present=True`` only when health says so.

    Pins the 3 audit-run verdicts the spec documents:
    - ``run_3383288d63e7``: all derivers ok/unknown → ``root_cause_present=False``
    - ``run_3cf6e7c036b3``: same → ``root_cause_present=False``
    - ``run_feb0f21ee770``: B-1 poisoned → ``root_cause_present=True``
      with ``root_cause_kind == "health_conditions_failed"``.
    """
    monkeypatch.chdir(tmp_path)
    healthy_ids = ["run_3383288d63e7", "run_3cf6e7c036b3"]
    for rid in healthy_ids:
        _write_spine(tmp_path, rid)
        payload = _invoke("explain", rid)
        assert payload["layer"] == "explain"
        assert payload["root_cause_present"] is False, (
            f"healthy run {rid} should have root_cause_present=False"
        )

    poisoned_id = "run_feb0f21ee770"
    _write_b1_spine(tmp_path, poisoned_id)
    payload = _invoke("explain", poisoned_id)
    assert payload["root_cause_present"] is True
    assert payload["root_cause_kind"] == "health_conditions_failed"
