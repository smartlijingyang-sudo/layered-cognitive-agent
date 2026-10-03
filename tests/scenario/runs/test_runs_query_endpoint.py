"""Tests for GET /runs/{run_id} querying and journal fallback."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.runs.api.query_endpoints import get_run


def test_get_run_fallback_from_journal_json(tmp_path: Path, monkeypatch) -> None:
    # Setup mock trace dir
    run_id = "run_test_fallback_123"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    journal_path = run_dir / "journal.json"
    journal_data = {
        "run_id": run_id,
        "trace_id": "trace_test_123",
        "started_at": 1791000000.0,
        "closed_at": 1791000010.0,
        "metadata": {
            "objective": "测试执行任务目标",
            "outcome": "completed",
        },
        "steps": [
            {
                "step_id": "step-001",
                "step_index": 1,
                "phase": "think",
                "duration_ms": 1500,
                "thinking": {
                    "model": "qwen3.7-plus",
                    "latency_ms": 1400,
                    "reasoning": "正在分析用户意图并选择合适工具...",
                    "decision": "use_tool",
                },
                "tool_call": {
                    "name": "runCommand",
                    "arguments": {"command": "ls -la"},
                    "arguments_summary": "command='ls -la'",
                },
                "tool_result": {
                    "ok": True,
                    "latency_ms": 10,
                    "stdout_head": "total 4\nfile1.txt",
                    "delta_summary": "✅ ok",
                },
            },
            {
                "step_id": "step-002",
                "step_index": 2,
                "phase": "think",
                "duration_ms": 2000,
                "thinking": {
                    "model": "qwen3.7-plus",
                    "latency_ms": 1900,
                    "reasoning": "文件列表已获取，向用户汇报结果。",
                    "decision": "respond",
                    "raw_response_preview": "目录中包含 file1.txt 文件。",
                },
            },
        ],
    }
    journal_path.write_text(json.dumps(journal_data), encoding="utf-8")

    # Mock _run_port_of to return None for summary (simulating session pruned from memory)
    mock_run_port = MagicMock()
    mock_run_port.summary = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "lca.plugins.transport.webserver.handlers.runs.api.query_endpoints._run_port_of",
        lambda req: mock_run_port,
    )
    monkeypatch.setattr(
        "lca.plugins.transport.webserver.handlers.runs.api.query_endpoints._DEFAULT_JOURNAL_ROOT",
        tmp_path,
    )

    app = Starlette(routes=[Route("/runs/{run_id}", get_run, methods=["GET"])])
    client = TestClient(app)

    resp = client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert data["question"] == "测试执行任务目标"
    assert data["output"] == "目录中包含 file1.txt 文件。"
    assert len(data["steps"]) == 2
    assert data["steps"][0]["thinking"]["model"] == "qwen3.7-plus"
    assert "正在分析用户意图" in data["steps"][0]["thinking"]["reasoning"]
    assert data["steps"][0]["tool_call"]["name"] == "runCommand"
    assert data["steps"][0]["tool_result"]["stdout_head"] == "total 4\nfile1.txt"

    # StepEvidence structure verification (INV-02, INV-05)
    step1_evidence = data["steps"][0].get("evidence")
    assert step1_evidence is not None
    assert step1_evidence["command"] == "ls -la"
    assert step1_evidence["duration_ms"] == 10
    assert step1_evidence["exit_code"] == 0
    assert "验证结论" in step1_evidence["conclusion"]
    assert "step_title" in step1_evidence


def test_get_run_404_when_missing(monkeypatch) -> None:
    mock_run_port = MagicMock()
    mock_run_port.summary = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "lca.plugins.transport.webserver.handlers.runs.api.query_endpoints._run_port_of",
        lambda req: mock_run_port,
    )

    app = Starlette(routes=[Route("/runs/{run_id}", get_run, methods=["GET"])])
    client = TestClient(app)

    resp = client.get("/runs/non_existent_run_999")
    assert resp.status_code == 404
    assert resp.json() == {"error": "run not found"}


def test_get_run_read_only_isolation(tmp_path: Path, monkeypatch) -> None:
    """Verifies INV-06: get_run is purely read-only and causes zero mutations."""
    run_id = "run_readonly_test"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    journal_path = run_dir / "journal.json"
    content = json.dumps({"run_id": run_id, "steps": []})
    journal_path.write_text(content, encoding="utf-8")

    mock_run_port = MagicMock()
    mock_run_port.summary = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "lca.plugins.transport.webserver.handlers.runs.api.query_endpoints._run_port_of",
        lambda req: mock_run_port,
    )
    monkeypatch.setattr(
        "lca.plugins.transport.webserver.handlers.runs.api.query_endpoints._DEFAULT_JOURNAL_ROOT",
        tmp_path,
    )

    app = Starlette(routes=[Route("/runs/{run_id}", get_run, methods=["GET"])])
    client = TestClient(app)

    resp = client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    # Assert journal.json content is untouched
    assert journal_path.read_text(encoding="utf-8") == content
