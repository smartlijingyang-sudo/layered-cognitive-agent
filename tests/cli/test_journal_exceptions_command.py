"""Tests for ``lca-ops journal exceptions`` subcommand.

锁定的不变量:
1. 默认读最新 run(``traces/runs`` 下 mtime 最新的目录)
2. ``--grep`` 按 exception_class 子串过滤
3. ``--json`` 输出 JSON 给 agent
4. 文件不存在时友好提示(exit 0)
5. 解析多行 traceback_text 为可读输出
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lca.infrastructure.cli.cli import app
from lca.infrastructure.observability.spine.sinks.tracing_file_sink import (
    TracingFileSink,
)

# ── helpers ──────────────────────────────────────────────────────────────


def _seed_run_with_exception(
    traces_root: Path,
    *,
    run_id: str = "run_test_exc",
    exc_class: str = "AttributeError",
    exc_message: str = "'str' object has no attribute 'value'",
) -> Path:
    """Create a run dir with <run_id>.exceptions.jsonl containing one event.

    ``traces_root`` 是 CLI 传入的 --traces-root 路径,布局:
    <traces_root>/runs/<run_id>/<run_id>.exceptions.jsonl
    """
    from datetime import datetime, timezone

    from lca.infrastructure.observability.spine.event_record import EventRecord

    runs_root = traces_root / "runs"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True)
    sink = TracingFileSink(run_dir, run_id=run_id)
    rec = EventRecord(
        execution_point="exception.caught",
        channel="error",
        span_id="lca-span-00000001",
        parent_span_id=None,
        sequence=1,
        epoch=1,
        causality_id="cu-1",
        outcome="failure",
        when=datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc),
        when_corrected=datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc),
        prev_event_hash=None,
        run_id=run_id,
        step_id="step-1",
        payload={
            "boundary": "lifecycle.fail_loud.AttributeError",
            "exception_class": exc_class,
            "exception_message": exc_message,
            "traceback_text": (
                "Traceback (most recent call last):\n"
                '  File "simple_body.py", line 117, in act\n'
                "    action_type=action_type.value\n"
                "AttributeError: 'str' object has no attribute 'value'"
            ),
            "source_location": {
                "file": "simple_body.py",
                "line": 117,
                "function": "act",
            },
            "run_id": run_id,
            "trace_id": "",
        },
    )
    sink.write(rec)
    sink.close()
    return run_dir


# ── tests ────────────────────────────────────────────────────────────────


def test_no_exceptions_file(tmp_path: Path) -> None:
    """run dir 存在但无 exceptions.jsonl → 友好提示。"""
    runner = CliRunner()
    traces_root = tmp_path / "traces"
    # Empty run dir
    (traces_root / "runs" / "run_empty").mkdir(parents=True)
    result = runner.invoke(app, ["journal", "exceptions", "--traces-root", str(traces_root)])
    assert result.exit_code == 0
    assert "无异常" in result.stdout or "不存在" in result.stdout


def test_list_exception(tmp_path: Path) -> None:
    """列出 traceback:人读格式。"""
    traces_root = tmp_path / "traces"
    _seed_run_with_exception(traces_root)
    runner = CliRunner()
    result = runner.invoke(app, ["journal", "exceptions", "--traces-root", str(traces_root)])
    assert result.exit_code == 0
    assert "AttributeError" in result.stdout
    assert "simple_body.py:117" in result.stdout
    assert "traceback" in result.stdout.lower()
    assert "count: 1" in result.stdout


def test_grep_filter(tmp_path: Path) -> None:
    """--grep ValueError 不匹配 AttributeError。"""
    traces_root = tmp_path / "traces"
    _seed_run_with_exception(traces_root)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "journal",
            "exceptions",
            "--traces-root",
            str(traces_root),
            "--grep",
            "ValueError",
        ],
    )
    assert result.exit_code == 0
    assert "无匹配" in result.stdout


def test_grep_match(tmp_path: Path) -> None:
    """--grep AttributeError 匹配。"""
    traces_root = tmp_path / "traces"
    _seed_run_with_exception(traces_root)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "journal",
            "exceptions",
            "--traces-root",
            str(traces_root),
            "--grep",
            "AttributeError",
        ],
    )
    assert result.exit_code == 0
    assert "AttributeError" in result.stdout
    assert "count: 1" in result.stdout


def test_json_output(tmp_path: Path) -> None:
    """--json 输出 JSON。"""
    traces_root = tmp_path / "traces"
    _seed_run_with_exception(traces_root)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "journal",
            "exceptions",
            "--traces-root",
            str(traces_root),
            "--json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["count"] == 1
    assert data["records"][0]["payload"]["exception_class"] == "AttributeError"


def test_spine_fallback_when_exceptions_index_missing(tmp_path: Path) -> None:
    """ADR-0183 SpineSink 路径无 exceptions.jsonl 时,回退读 spine.jsonl。"""
    runner = CliRunner()
    traces_root = tmp_path / "traces"
    run_id = "run_spine_only"
    run_dir = traces_root / "runs" / run_id
    run_dir.mkdir(parents=True)
    spine_path = run_dir / f"{run_id}.spine.jsonl"
    spine_path.write_text(
        json.dumps(
            {
                "execution_point": "exception.caught",
                "channel": "error",
                "payload": {
                    "exception_class": "ValidationError",
                    "exception_message": "bad payload",
                    "boundary": "act.main",
                    "traceback_text": "Traceback...\nValidationError: bad payload",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["journal", "exceptions", run_id, "--traces-root", str(traces_root), "--json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["source"] == "spine_fallback"
    assert data["count"] == 1
    assert data["records"][0]["payload"]["exception_class"] == "ValidationError"
