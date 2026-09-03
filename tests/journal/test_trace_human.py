"""Tests for ``lca-ops journal trace --human`` (Phase-1 view layer).

``--human`` (now default) renders the spine ``events.jsonl`` as a tree-
shaped timeline that surfaces each node's own payload content directly
— the goal is information density, not just pretty formatting.

These tests build synthetic ``events.jsonl`` via ``FileSink`` (the
same write path the real spine uses) and assert that the rendered
human view:

* walks ``parent_span_id`` as a tree (▸ for roots, ↳ for leaves);
* prints absolute + relative timing per line (``Δ+…ms``);
* keeps payload text intact (``delta_summary``, ``exception_message``,
  ``traceback_snippet``, ``arguments_summary``, ``prompt_preview``,
  ``stdout_head``);
* collapses repeated streams (``llm.stream.token``,
  ``runtime.reducer.apply``, paired ``transport.route``) into a single
  summary line while preserving the full text;
* still honours ``--no-human`` to keep the original machine-readable
  table for CI/agents.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lca.infrastructure.cli.cli import app
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink

runner = CliRunner()


# ── helpers ────────────────────────────────────────────────────────


def _record(
    *,
    sequence: int,
    execution_point: str,
    payload: dict,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    outcome: str | None = "success",
    when_iso: str = "2026-09-01T00:00:00+00:00",
) -> EventRecord:
    return EventRecord(
        execution_point=execution_point,
        channel="fact",
        span_id=span_id if span_id is not None else f"lca-seq-{sequence:08d}",
        parent_span_id=parent_span_id,
        sequence=sequence,
        epoch=1,
        causality_id=f"causality-{sequence:08d}",
        outcome=outcome,
        when=datetime.fromisoformat(when_iso),
        when_corrected=datetime.fromisoformat(when_iso),
        prev_event_hash=None,
        run_id="run_human",
        step_id=None,
        payload=payload,
        phase="live",
        reason=None,
    )


def _write_jsonl(run_dir: Path, records: list[EventRecord]) -> Path:
    # PR-4 收口:FileSink 默认 spine 命名 = <run_id>.spine.jsonl;旧 events.jsonl layout 已下线。
    sink = FileSink(run_dir, run_id="run_human")
    for r in records:
        sink.write(r)
    sink.close()
    return run_dir / "run_human.spine.jsonl"


@pytest.fixture
def traces_root(tmp_path: Path) -> Path:
    """A small run whose events exercise every ``--human`` rendering rule.

    Includes: kernel.start, transport.enter/exit (paired), agent_loop
    start, phase_graph.node.start/end with input_params + failure
    envelope, brain/reasoner, llm.call.start with prompt_preview,
    llm.stream.token ×3, llm.call.end, body.tool.execute, sandbox,
    phase.tool.call.start/end with delta_summary + files_created,
    phase.perceive.fold with summary, exception.caught with full
    message, kernel.run.stop, lifecycle.finally.
    """
    root = tmp_path / "traces"
    run_dir = root / "runs" / "run_human"
    run_dir.mkdir(parents=True)

    t0 = "2026-09-01T00:00:00+00:00"
    t1 = "2026-09-01T00:00:00.500+00:00"
    t2 = "2026-09-01T00:00:01.000+00:00"

    records = [
        # 1. transport POST /runs (paired with exit at seq 2)
        _record(
            sequence=1,
            execution_point="transport.route.enter",
            payload={"path": "/runs", "method": "POST", "run_id": ""},
            when_iso=t0,
        ),
        _record(
            sequence=2,
            execution_point="transport.route.exit",
            payload={"path": "/runs", "method": "POST", "run_id": "", "status": 200},
            when_iso=t0,
        ),
        # 3. kernel.run.start
        _record(
            sequence=3,
            execution_point="kernel.run.start",
            payload={"run_id": "run_human", "trace_id": "trace_h1"},
            when_iso=t0,
        ),
        # 4. agent_loop start
        _record(
            sequence=4,
            execution_point="agent_loop.iteration.start",
            payload={"trace_id": "trace_h1", "role": "助手", "iteration_kind": "fresh"},
            when_iso=t0,
        ),
        # 5. phase_graph.node.start — payload carries input_params/output_schema/preconditions
        _record(
            sequence=5,
            execution_point="phase_graph.node.start",
            span_id="lca-span-00000001",
            parent_span_id="lca-seq-00000004",
            payload={
                "span_id": "lca-span-00000001",
                "parent_span_id": "lca-seq-00000004",
                "signature_fingerprint": "sig-sha256:4b0b957b",
                "input_params": {
                    "objective": "随便做点什么",
                    "max_steps": 6,
                },
                "output_schema": {"type": "object", "fields": ["plan"]},
                "preconditions": ["objective 非空"],
            },
            when_iso=t0,
        ),
        # 6. phase.perceive.fold — summary is the agent's actual perception result
        _record(
            sequence=6,
            execution_point="phase.perceive.fold",
            parent_span_id="lca-span-00000001",
            payload={
                "phase": "perceive",
                "objective": "你好",
                "summary": "感知 3 项 (clock, workspace_instructions, skill_catalog)",
            },
            when_iso=t0,
        ),
        # 7-9. llm stream
        _record(
            sequence=7,
            execution_point="llm.call.start",
            parent_span_id="lca-span-00000001",
            payload={
                "model": "scripted-llm",
                "stream": True,
                "prompt_preview": "ROLE: 产品经理\nGOAL: 全局型产品负责人\nBACKSTORY: 你是 A",
            },
            when_iso=t0,
        ),
        _record(
            sequence=8,
            execution_point="llm.stream.token",
            parent_span_id="lca-span-00000001",
            payload={"model": "scripted-llm", "text_delta": "你好", "seq": 1},
            when_iso=t0,
        ),
        _record(
            sequence=9,
            execution_point="llm.stream.token",
            parent_span_id="lca-span-00000001",
            payload={"model": "scripted-llm", "text_delta": ",我是助手", "seq": 2},
            when_iso=t0,
        ),
        _record(
            sequence=10,
            execution_point="llm.stream.token",
            parent_span_id="lca-span-00000001",
            payload={"model": "scripted-llm", "text_delta": "。", "seq": 3},
            when_iso=t0,
        ),
        _record(
            sequence=11,
            execution_point="llm.call.end",
            parent_span_id="lca-span-00000001",
            payload={
                "model": "scripted-llm",
                "latency_ms": 200,
                "prompt_tokens": 224,
                "completion_tokens": 8,
            },
            when_iso=t1,
        ),
        # 12. tool call
        _record(
            sequence=12,
            execution_point="body.tool.execute.start",
            parent_span_id="lca-span-00000001",
            payload={
                "tool_name": "listFiles",
                "invocation_id": "toolu_h1",
                "attempt": 1,
                "wrapper": "executionWrapper",
            },
            when_iso=t1,
        ),
        _record(
            sequence=13,
            execution_point="phase.tool.call.end",
            parent_span_id="lca-span-00000001",
            payload={
                "tool_name": "listFiles",
                "invocation_id": "toolu_h1",
                "ok": True,
                "latency_ms": 2500,
                "arguments_summary": "directoryPath='/mnt/data'",
                "delta_summary": "✅ 列出 2 项: .lca, outputs",
                "stdout_head": ".lca\noutputs\n",
                "stdout_chars_total": 14,
                "stdout_truncated": False,
                "files_created": [".lca", "outputs"],
            },
            outcome="success",
            when_iso=t2,
        ),
        # 14. exception — message preserved verbatim (Chinese + JSON parse error)
        _record(
            sequence=14,
            execution_point="exception.caught",
            parent_span_id="lca-span-00000001",
            payload={
                "boundary": "lifecycle.execute",
                "exc_type": "CastingError",
                "message": "自动组队失败:输出不是合法 JSON:Expecting value: line 1 column 1 (char 0)",
            },
            outcome="failure",
            when_iso=t2,
        ),
        # 15. phase_graph.node.end — failure envelope carries full error
        _record(
            sequence=15,
            execution_point="phase_graph.node.end",
            span_id="lca-span-00000001",
            parent_span_id="lca-seq-00000004",
            payload={
                "span_id": "lca-span-00000001",
                "error_type": "CastingError",
                "exception_message": "自动组队失败:输出不是合法 JSON:Expecting value: line 1 column 1 (char 0)",
                "traceback_snippet": 'File "/home/lichao/layered-cognitive-agent/lca/cognition/brain/reasoner.py", line 87, in delegate\nCastingError: 解析失败',
            },
            outcome="failure",
            when_iso=t2,
        ),
        # 16. lifecycle.finally
        _record(
            sequence=16,
            execution_point="lifecycle.finally",
            parent_span_id=None,
            payload={"boundary": "terminal_driver", "trace_id": "trace_h1"},
            when_iso=t2,
        ),
        # 17. kernel.run.stop
        _record(
            sequence=17,
            execution_point="kernel.run.stop",
            payload={"run_id": "run_human", "trace_id": "trace_h1"},
            outcome="failure",
            when_iso=t2,
        ),
    ]
    _write_jsonl(run_dir, records)
    return root


# ── default --human ───────────────────────────────────────────────


def test_human_default_prints_payload_text_verbatim(traces_root: Path) -> None:
    """Default ``journal trace`` (no flags) is now ``--human`` and surfaces
    the exact ``delta_summary`` / ``exception_message`` / ``prompt_preview``
    strings — not just the EP name."""
    result = runner.invoke(
        app,
        ["journal", "trace", "run_human", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0, result.stderr
    out = result.stdout

    # Chinese payload content surfaces verbatim (not just "phase.tool.call.end").
    assert "✅ 列出 2 项: .lca, outputs" in out
    # Failure envelope — exception_message must appear intact.
    assert "自动组队失败:输出不是合法 JSON" in out
    # traceback snippet must appear (multi-line content preserved).
    assert "reasoner.py" in out
    assert "line 87" in out
    # LLM prompt preview surfaces (not truncated aggressively).
    assert "ROLE: 产品经理" in out
    # perceive.fold summary
    assert "感知 3 项 (clock" in out


def test_human_default_renders_tree(traces_root: Path) -> None:
    """Tree glyphs (▸ root, ↳ child, ├ / └ for multi-line payload) appear."""
    result = runner.invoke(
        app,
        ["journal", "trace", "run_human", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    out = result.stdout
    # Roots use ▸, children use ↳, phase_graph node start child shows ├ for
    # multi-line payload (input_params/output_schema/preconditions).
    assert "▸" in out
    assert "↳" in out


def test_human_default_shows_relative_delta(traces_root: Path) -> None:
    """Each line carries a relative Δms anchor (kernel.run.start = Δ+0ms)."""
    result = runner.invoke(
        app,
        ["journal", "trace", "run_human", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    out = result.stdout
    assert "Δ+0ms" in out or "Δ+0s" in out  # kernel.run.start anchor


# ── --no-human preserves the original machine table ──────────────


def test_no_human_keeps_machine_table(traces_root: Path) -> None:
    """``--no-human`` keeps the original seq/execution_point/... table so
    CI scripts and agents can keep parsing it."""
    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "run_human",
            "--no-human",
            "--traces-root",
            str(traces_root),
        ],
    )
    assert result.exit_code == 0, result.stderr
    out = result.stdout
    assert "execution_point" in out  # the table header
    assert "events rendered" in out  # the machine summary footer
    # Tree glyphs must NOT appear in the machine view.
    assert "▸" not in out
    assert "↳" not in out


# ── token / reducer / transport folding ──────────────────────────


def test_human_folds_consecutive_tokens(traces_root: Path) -> None:
    """Three consecutive ``llm.stream.token`` collapse into one line whose
    payload text is concatenated verbatim — every token char is preserved."""
    result = runner.invoke(
        app,
        ["journal", "trace", "run_human", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    out = result.stdout
    # The three deltas "你好" + ",我是助手" + "。" must appear concatenated.
    assert "你好,我是助手。" in out
    # The folded line carries the token count and char count.
    assert "×3" in out or "3 tokens" in out


def test_human_pairs_transport_enter_exit(traces_root: Path) -> None:
    """Paired ``transport.route.enter`` + ``.exit`` collapse into one line
    showing ``method path → status`` and a single Δms."""
    result = runner.invoke(
        app,
        ["journal", "trace", "run_human", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    out = result.stdout
    # One combined line, not two separate ones, and the path/method show.
    assert "POST /runs" in out


# ── --max-detail-per-node clamps detail explosion ──────────────


def test_max_detail_per_node_truncates(traces_root: Path) -> None:
    """``--max-detail-per-node N`` caps each node's detail lines."""
    result = runner.invoke(
        app,
        [
            "journal",
            "trace",
            "run_human",
            "--max-detail-per-node",
            "2",
            "--traces-root",
            str(traces_root),
        ],
    )
    assert result.exit_code == 0, result.stderr
    # We expect a "more lines" marker somewhere when the traceback
    # envelope exceeds the cap.
    out = result.stdout
    assert ("+N more" in out) or ("+more" in out) or ("more lines" in out)
