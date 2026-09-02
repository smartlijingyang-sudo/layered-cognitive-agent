"""CLI journal step-tree viewer 单测(ADR-0164 草案 Phase 5)。

覆盖:
- journal steps <id> 列 step 表
- journal steps <id> --step N 显单步
- journal steps <id> --summary 列因果链
- journal steps <id> --json 输出 JournalDocument JSON
- journal narrative <id> 输出 narrative.md
- journal raw <id> 输出 journal.raw.jsonl
- 文件不存在友好错误 + typer.Exit(1)
- --traces-root flag 解析
- 中文 / Unicode 原样保留
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lca.contracts.models.observability import (
    JournalMetadata,
    JournalStep,
    ReflectTrace,
    StepContext,
    append_step,
    close_document,
    empty_document,
)
from lca.infrastructure.cli.cli import app
from lca.infrastructure.observability.journal.step.narrative_writer import (
    StepNarrativeWriter,
)
from lca.infrastructure.observability.journal.step.projector import (
    JournalDocumentWriter,
)

runner = CliRunner()


def _build_doc() -> object:
    """构造 2 步样本(perceive + think 中文 objective)。"""
    meta = JournalMetadata(
        agent_role="agt_test",
        strategy_key="solo",
        plan_ref="plan_001",
        objective="分析生成pdf版本",
    )
    doc = empty_document(run_id="r1", trace_id="t1", metadata=meta, started_at=0.0)
    s1 = JournalStep(
        step_id="step_1",
        step_index=1,
        phase="perceive",
        entered_at=0.0,
        exited_at=0.5,
        duration_ms=500,
        context_before=StepContext(objective="分析生成pdf版本"),
        reflect=ReflectTrace(summary="读取 sheet 完成"),
        outcome="ok",
    )
    s2 = JournalStep(
        step_id="step_2",
        step_index=2,
        phase="think",
        entered_at=0.5,
        exited_at=1.0,
        duration_ms=500,
        context_before=StepContext(
            objective="分析生成pdf版本",
            prior_summary_chain=("ok (perceive): 读取 sheet 完成",),
        ),
        reflect=ReflectTrace(summary="决定 use_tool"),
        outcome="ok",
    )
    doc = append_step(doc, s1)
    doc = append_step(doc, s2)
    return close_document(doc, outcome="completed", closed_at=2.0)


@pytest.fixture
def traces_root(tmp_path: Path) -> Path:
    """布置 traces 目录 + run dir + journal.json + narrative.md。"""
    root = tmp_path / "traces"
    run_dir = root / "runs" / "r1"
    run_dir.mkdir(parents=True)
    doc = _build_doc()
    JournalDocumentWriter(run_dir / "journal.json").write(doc)
    StepNarrativeWriter(run_dir / "journal.narrative.md").write(doc)
    # 兜底 raw 也写一份(测试 raw 命令)
    (run_dir / "journal.jsonl").write_text('{"legacy": true}\n', encoding="utf-8")
    return root


# ── steps 命令 ──


def test_steps_default_shows_table(traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "steps", "r1", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    assert "分析生成pdf版本" in result.stdout
    assert "run_id=r1" in result.stdout
    assert "step_1" not in result.stdout  # step_id 不在表格
    assert "1" in result.stdout  # step_index
    assert "perceive" in result.stdout
    assert "think" in result.stdout


def test_steps_shows_outcome_icons(traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "steps", "r1", "--traces-root", str(traces_root)],
    )
    assert "✓" in result.stdout  # ok
    assert result.exit_code == 0


def test_steps_step_index_shows_detail(traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "steps", "r1", "--step", "1", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    assert "读取 sheet 完成" in result.stdout
    assert "**上下文**:" in result.stdout
    assert "**反思**:" in result.stdout


def test_steps_step_index_out_of_range(traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "steps", "r1", "--step", "999", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 1
    assert "不存在" in result.output


def test_steps_summary_shows_chain(traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "steps", "r1", "--summary", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    assert "ok (perceive): 读取 sheet 完成" in result.stdout
    assert "ok (think): 决定 use_tool" in result.stdout


def test_steps_json_outputs_full_document(traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "steps", "r1", "--json", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema"] == "lca.journal/3"
    assert payload["run_id"] == "r1"
    assert len(payload["steps"]) == 2


def test_steps_missing_file_friendly_error(traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "steps", "missing", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 1
    assert "not found" in result.output


# ── narrative 命令 ──


def test_narrative_outputs_markdown(traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "narrative", "r1", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    assert "# Run Narrative —— 分析生成pdf版本" in result.stdout
    assert "## 📊 Summary" in result.stdout


def test_narrative_missing_file_friendly_error(traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "narrative", "missing", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 1
    assert "not found" in result.output


# ── raw 命令 ──


def test_raw_outputs_legacy_jsonl(traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "raw", "r1", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 0
    assert '{"legacy": true}' in result.stdout


def test_raw_missing_file_friendly_error(traces_root: Path) -> None:
    """raw 默认不存在 → 友好错误, 不假退化为 steps。"""
    # 删 raw 文件
    (traces_root / "runs" / "r1" / "journal.jsonl").unlink()
    result = runner.invoke(
        app,
        ["journal", "raw", "r1", "--traces-root", str(traces_root)],
    )
    assert result.exit_code == 1
    assert "not found" in result.output


# ── logs 命令仍存在 (向后兼容) ──


def test_logs_command_still_exists() -> None:
    result = runner.invoke(app, ["journal", "logs", "--help"])
    assert result.exit_code == 0
    assert "事实流" in result.stdout or "journal" in result.stdout


# ── 中文处理 ──


def test_chinese_preserved_in_table(traces_root: Path) -> None:
    result = runner.invoke(
        app,
        ["journal", "steps", "r1", "--traces-root", str(traces_root)],
    )
    assert "分析生成pdf版本" in result.stdout
    assert "读取 sheet 完成" in result.stdout
    assert "决定 use_tool" in result.stdout
