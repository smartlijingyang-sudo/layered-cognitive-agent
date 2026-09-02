"""Doctor H6 surfaces session.error when journal stream is empty."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lca.plugins.transport.webserver.handlers.runs.doctor.legacy import hop_h6
from lca.plugins.transport.webserver.handlers.runs.doctor.models import JsonlScan
from lca.plugins.tools.diagnostics.debug_run import _extract_failure


def test_hop_h6_surfaces_session_error_when_journal_empty() -> None:
    session = SimpleNamespace(error="MemoryView.__init__() missing 1 required positional argument: 'buffer'")
    scan = JsonlScan(
        exists=False,
        rows=0,
        last_seq=0,
        counts={},
        has_finished=False,
        finished_error="",
        journal_status="",
        output_text="",
        output_text_explicit=False,
        has_attachment=False,
        unpaired_tools=(),
        tool_total=0,
        tool_success=0,
        max_consecutive_fail=0,
        missing_plugin_state=(),
    )
    verdict = hop_h6(session, scan)
    assert verdict.ok is False
    assert "carrier failure" in (verdict.detail or "")
    assert "MemoryView" in (verdict.extra or {}).get("error", "")


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
