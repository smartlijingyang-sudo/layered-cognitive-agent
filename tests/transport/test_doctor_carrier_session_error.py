"""Doctor surfaces session.error via debug-run extraction when journal missing.

Legacy journal.jsonl H6 fallback 已下线;step-tree 路径无 journal 时由
debug-run 通过 manifest.session_error 抽取故障信息。
"""

from __future__ import annotations

from pathlib import Path

from lca.plugins.tools.diagnostics.debug_run import _extract_failure


def test_debug_run_extract_failure_reads_session_error() -> None:
    manifest = {
        "extra": {
            "doctor_report": {"hops": {"H6": {"error": ""}}},
            "session_error": "MemoryView.__init__() missing 1 required positional argument: 'buffer'",
        }
    }
    _node, message, _etype = _extract_failure(manifest, [])
    assert message is not None
    assert "MemoryView" in message


def test_record_run_failure_writes_kernel_log(tmp_path: Path, monkeypatch) -> None:
    from lca.plugins.transport.webserver.handlers.runs.terminal.failure import (
        RunFailureFacts,
        record_run_failure,
    )

    monkeypatch.chdir(tmp_path)
    record_run_failure(
        RunFailureFacts(
            trace_id="trace_x",
            run_id="run_carrier_fail",
            agent_role="agent",
            strategy_key="solo",
            objective="hello",
            error="MemoryView.__init__() missing buffer",
        )
    )
    log_path = tmp_path / "traces" / "runs" / "run_carrier_fail" / "kernel.log"
    assert log_path.exists()
    assert "MemoryView" in log_path.read_text()
