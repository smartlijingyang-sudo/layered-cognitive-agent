"""JournalMigrator 单测(ADR-0164 草案 Phase 6)。

覆盖:
- 单 run 完整 migrate (AgentRunStarted → ContextManifested → LLM → 多个 tool → Finish)
- LlmCallCompleted + 后续 ToolStarted 同 scope.step → 1 个 think step
- ToolInvoked fail → step.outcome=fail + error
- 未分类事件 → 放进最近 step 的 spans
- migration_inferred=true 在 metadata
- 文件不存在友好错误
- dry-run 不写文件
- --all 跑所有 run
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lca.infrastructure.cli.cli import app
from lca.infrastructure.observability.journal.step.migrate import (
    JournalMigrator,
    iter_run_ids,
    migrate_run,
)

runner = CliRunner()


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """写多行 pretty JSON (跟真实 journal.jsonl 一样)。"""
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, indent=2, ensure_ascii=False) + "\n\n")


def _agent_run_started(run_id: str, trace_id: str, objective: str = "test") -> dict:
    return {
        "schema": "lca.journal/2",
        "run_seq": 1,
        "descriptor": {"type": "AgentRunStarted"},
        "scope": {"trace_id": trace_id, "run_id": run_id, "agent_role": "agt", "step": 0},
        "occurred_at": 1000.0,
        "data": {"objective": objective, "objective_preview": objective[:30]},
    }


def _context_manifested(run_id: str, trace_id: str, scope_step: int = 1) -> dict:
    return {
        "schema": "lca.journal/2",
        "run_seq": 2,
        "descriptor": {"type": "ContextManifested"},
        "scope": {"trace_id": trace_id, "run_id": run_id, "agent_role": "agt", "step": scope_step},
        "occurred_at": 1001.0,
        "data": {"step": scope_step, "item_kinds": ["uploaded_file"]},
    }


def _llm_completed(run_id: str, trace_id: str, scope_step: int, **kw) -> dict:
    return {
        "schema": "lca.journal/2",
        "run_seq": 3,
        "descriptor": {"type": "LlmCallCompleted"},
        "scope": {"trace_id": trace_id, "run_id": run_id, "agent_role": "agt", "step": scope_step},
        "occurred_at": kw.get("ts", 1010.0),
        "data": {
            "model": kw.get("model", "qwen3.7-plus"),
            "latency_ms": kw.get("latency_ms", 5000),
            "decision": kw.get("decision", "use_tool"),
            "reasoning_preview": kw.get("reasoning", "thinking"),
            "response_preview": kw.get("response", "ok"),
            "prompt_tokens": kw.get("prompt_tokens", 100),
            "completion_tokens": kw.get("completion_tokens", 50),
        },
    }


def _tool_invoked(run_id: str, trace_id: str, scope_step: int, *, ok: bool = True, **kw) -> dict:
    inv = kw.get("invocation_id", "t1")
    tool_name = kw.get("tool_name", "executeCode")
    return {
        "schema": "lca.journal/2",
        "run_seq": 4,
        "descriptor": {"type": "ToolInvoked"},
        "scope": {"trace_id": trace_id, "run_id": run_id, "agent_role": "agt", "step": scope_step},
        "occurred_at": kw.get("ts", 1015.0),
        "data": {
            "tool_name": tool_name,
            "invocation_id": inv,
            "ok": ok,
            "latency_ms": kw.get("latency_ms", 4500),
            "output_text": kw.get("output_text", "ok"),
            "files": kw.get("files", []),
            "error": kw.get("error", "") if not ok else "",
        },
    }


def _agent_finished(run_id: str, trace_id: str, *, status: str = "completed") -> dict:
    return {
        "schema": "lca.journal/2",
        "run_seq": 99,
        "descriptor": {"type": "AgentRunFinished"},
        "scope": {"trace_id": trace_id, "run_id": run_id, "agent_role": "agt", "step": 2},
        "occurred_at": 1030.0,
        "data": {"status": status, "output_text": "完成"},
    }


@pytest.fixture
def tmp_traces_root(tmp_path: Path) -> Path:
    return tmp_path / "traces"


# ── 单元测试:JournalMigrator ──


def test_migrator_minimal_run() -> None:
    """最小 run:AgentRunStarted → LLMCallCompleted → ToolInvoked → AgentRunFinished"""
    migrator = JournalMigrator(run_id="r1", trace_id="t1")
    migrator.feed(_agent_run_started("r1", "t1"))
    migrator.feed(_llm_completed("r1", "t1", 1))
    migrator.feed(_tool_invoked("r1", "t1", 1, ok=True))
    migrator.feed(_agent_finished("r1", "t1", status="completed"))
    doc = migrator.finalize()
    assert doc.metadata.outcome == "completed"
    # step 1 = LLM think + tool
    assert len(doc.steps) >= 1
    s1 = doc.step_by_index(1)
    assert s1 is not None
    assert s1.thinking is not None
    assert s1.thinking.model == "qwen3.7-plus"
    assert s1.tool_result is not None
    assert s1.tool_result.ok is True


def test_migrator_failed_tool() -> None:
    migrator = JournalMigrator(run_id="r1", trace_id="t1")
    migrator.feed(_agent_run_started("r1", "t1"))
    migrator.feed(_llm_completed("r1", "t1", 1))
    migrator.feed(_tool_invoked("r1", "t1", 1, ok=False, error="boom"))
    migrator.feed(_agent_finished("r1", "t1", status="failed"))
    doc = migrator.finalize()
    assert doc.metadata.outcome == "failed"
    # step 1 outcome fail
    s1 = doc.step_by_index(1)
    assert s1 is not None
    assert s1.outcome == "fail"
    assert s1.tool_result is not None
    assert s1.tool_result.error == "boom"


def test_migrator_two_steps_with_phase_upgrade() -> None:
    """step 1 (perceive→think) + step 2 (act)"""
    migrator = JournalMigrator(run_id="r1", trace_id="t1")
    migrator.feed(_agent_run_started("r1", "t1"))
    # step 1: ContextManifested (perceive) + LLM (think) + tool ok
    migrator.feed(_context_manifested("r1", "t1", 1))
    migrator.feed(_llm_completed("r1", "t1", 1))
    migrator.feed(_tool_invoked("r1", "t1", 1, ok=True, invocation_id="t1"))
    # step 2: tool fail
    migrator.feed(_tool_invoked("r1", "t1", 2, ok=False, invocation_id="t2", error="LayoutError"))
    migrator.feed(_agent_finished("r1", "t1", status="failed"))
    doc = migrator.finalize()
    assert len(doc.steps) == 2
    # step 1 phase = think (LLM 主导)
    s1 = doc.step_by_index(1)
    assert s1 is not None
    assert s1.phase == "think"
    # step 2 phase = act
    s2 = doc.step_by_index(2)
    assert s2 is not None
    assert s2.phase == "act"
    assert s2.outcome == "fail"


def test_migrator_inferred_marker() -> None:
    migrator = JournalMigrator(run_id="r1", trace_id="t1")
    migrator.feed(_agent_run_started("r1", "t1"))
    migrator.feed(_llm_completed("r1", "t1", 1))
    migrator.feed(_agent_finished("r1", "t1"))
    doc = migrator.finalize()
    assert doc.metadata.extra.get("migration_inferred") is True


def test_migrator_unknown_events_go_to_spans() -> None:
    """未分类事件 → 最近 step 的 spans"""
    migrator = JournalMigrator(run_id="r1", trace_id="t1")
    migrator.feed(_agent_run_started("r1", "t1"))
    migrator.feed(_llm_completed("r1", "t1", 1))
    # 未在白名单的事件
    migrator.feed(
        {
            "schema": "lca.journal/2",
            "descriptor": {"type": "RunActivity"},
            "scope": {"trace_id": "t1", "run_id": "r1", "agent_role": "agt", "step": 1},
            "occurred_at": 1011.0,
            "data": {"kind": "act", "phase": "act"},
        }
    )
    migrator.feed(_agent_finished("r1", "t1"))
    doc = migrator.finalize()
    s1 = doc.step_by_index(1)
    assert s1 is not None
    assert any(span.kind == "runactivity" for span in s1.spans)


def test_migrator_objective_captured() -> None:
    migrator = JournalMigrator(run_id="r1", trace_id="t1")
    migrator.feed(_agent_run_started("r1", "t1", objective="分析xlsx"))
    migrator.feed(_llm_completed("r1", "t1", 1))
    migrator.feed(_agent_finished("r1", "t1"))
    doc = migrator.finalize()
    assert "分析xlsx" in doc.metadata.objective


# ── 文件级测试:migrate_run ──


def test_migrate_run_writes_journal_and_narrative(tmp_traces_root: Path) -> None:
    run_dir = tmp_traces_root / "runs" / "r1"
    run_dir.mkdir(parents=True)
    _write_jsonl(
        run_dir / "journal.jsonl",
        [
            _agent_run_started("r1", "t1"),
            _llm_completed("r1", "t1", 1),
            _tool_invoked("r1", "t1", 1, ok=True),
            _agent_finished("r1", "t1"),
        ],
    )
    jp, np = migrate_run(tmp_traces_root, "r1")
    assert jp.exists()
    assert np.exists()
    # 原 jsonl 保留
    assert (run_dir / "journal.jsonl").exists()


def test_migrate_run_missing_file_raises(tmp_traces_root: Path) -> None:
    (tmp_traces_root / "runs").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        migrate_run(tmp_traces_root, "missing")


def test_iter_run_ids(tmp_traces_root: Path) -> None:
    runs = tmp_traces_root / "runs"
    runs.mkdir(parents=True)
    for rid in ("r1", "r2", "r3"):
        run_dir = runs / rid
        run_dir.mkdir()
        (run_dir / "journal.jsonl").write_text("{}", encoding="utf-8")
    # 一个没 jsonl 的目录应被跳过
    (runs / "empty").mkdir()
    ids = list(iter_run_ids(tmp_traces_root))
    assert ids == ["r1", "r2", "r3"]


# ── CLI 测试 ──


def test_cli_migrate_dry_run(tmp_traces_root: Path) -> None:
    run_dir = tmp_traces_root / "runs" / "r1"
    run_dir.mkdir(parents=True)
    _write_jsonl(
        run_dir / "journal.jsonl",
        [_agent_run_started("r1", "t1"), _agent_finished("r1", "t1")],
    )
    result = runner.invoke(
        app,
        ["journal", "migrate", "r1", "--dry-run", "--traces-root", str(tmp_traces_root)],
    )
    assert result.exit_code == 0
    assert "2 records" in result.stdout
    # dry-run 不写文件
    assert not (run_dir / "journal.json").exists()


def test_cli_migrate_run(tmp_traces_root: Path) -> None:
    run_dir = tmp_traces_root / "runs" / "r1"
    run_dir.mkdir(parents=True)
    _write_jsonl(
        run_dir / "journal.jsonl",
        [
            _agent_run_started("r1", "t1"),
            _llm_completed("r1", "t1", 1),
            _tool_invoked("r1", "t1", 1, ok=True),
            _agent_finished("r1", "t1"),
        ],
    )
    result = runner.invoke(
        app,
        ["journal", "migrate", "r1", "--traces-root", str(tmp_traces_root)],
    )
    assert result.exit_code == 0
    assert (run_dir / "journal.json").exists()
    assert (run_dir / "journal.narrative.md").exists()
    assert (run_dir / "journal.jsonl").exists()  # 保留


def test_cli_migrate_all(tmp_traces_root: Path) -> None:
    runs = tmp_traces_root / "runs"
    runs.mkdir(parents=True)
    for rid in ("r1", "r2"):
        run_dir = runs / rid
        run_dir.mkdir()
        _write_jsonl(
            run_dir / "journal.jsonl",
            [
                _agent_run_started(rid, "t"),
                _llm_completed(rid, "t", 1),
                _agent_finished(rid, "t"),
            ],
        )
    result = runner.invoke(
        app,
        ["journal", "migrate", "--all", "--traces-root", str(tmp_traces_root)],
    )
    assert result.exit_code == 0
    assert (runs / "r1" / "journal.json").exists()
    assert (runs / "r2" / "journal.json").exists()


def test_cli_migrate_missing_run(tmp_traces_root: Path) -> None:
    (tmp_traces_root / "runs").mkdir(parents=True)
    result = runner.invoke(
        app,
        ["journal", "migrate", "missing", "--traces-root", str(tmp_traces_root)],
    )
    assert result.exit_code == 0  # friendly, not crash
    assert "journal.jsonl" in result.output  # "not found" message


def test_cli_migrate_requires_target(tmp_traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "migrate", "--traces-root", str(tmp_traces_root)],
    )
    assert result.exit_code == 1
    assert "传 run_id 或 --all" in result.output
