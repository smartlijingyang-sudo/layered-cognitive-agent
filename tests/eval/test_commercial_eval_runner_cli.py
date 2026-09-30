"""验证商用多轮评测双模 CLI 运行器命令行行为与离线断言。"""
# ruff: noqa: S603

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_RUNNER_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_commercial_eval.py"


def test_cli_runner_help() -> None:
    cmd = [sys.executable, str(_RUNNER_PATH), "--help"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "--mock" in proc.stdout
    assert "--all" in proc.stdout
    assert "--case" in proc.stdout
    assert "--report" in proc.stdout


def test_cli_runner_list() -> None:
    cmd = [sys.executable, str(_RUNNER_PATH), "--list"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "MEM_CROSS_TOPIC_REMIND" in proc.stdout
    assert "DREAMING_CONFLICT_RECONCILIATION" in proc.stdout
    assert "共 16 套多轮对话场景" in proc.stdout


def test_cli_runner_mock_all_scenarios() -> None:
    cmd = [sys.executable, str(_RUNNER_PATH), "--mock", "--all"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, f"Runner failed with: {proc.stderr}"
    assert "16 passed, 0 failed" in proc.stdout
    assert "muse_memory" in proc.stdout
    assert "grok_wit" in proc.stdout
    assert "hermes_tools" in proc.stdout


def test_cli_runner_mock_single_case() -> None:
    cmd = [
        sys.executable,
        str(_RUNNER_PATH),
        "--mock",
        "--case",
        "MEM_CROSS_TOPIC_REMIND",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "MEM_CROSS_TOPIC_REMIND" in proc.stdout
    assert "PASS" in proc.stdout


def test_cli_runner_mock_generate_report(tmp_path: Path) -> None:
    report_file = tmp_path / "test_scorecard.md"
    cmd = [
        sys.executable,
        str(_RUNNER_PATH),
        "--mock",
        "--all",
        "--report",
        str(report_file),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "商用级旗舰 Agent 多轮对话全景评测战力看板" in content
    assert "16 / 16 (100.0%)" in content
