"""Test that emit_diagnostic G-14 fix is applied correctly.

Verifies spec §15 G-14:
- default status is "info" (not "failed")
- 5 call sites pass explicit DiagnosticStatus (3 in tool_journal.py, 2 in perceive/hub.py)
"""
from __future__ import annotations

import inspect
from pathlib import Path


def test_emit_diagnostic_default_status_is_info():
    """The default status argument should be 'info', not 'failed'."""
    from lca.infrastructure.session.commit.fact_committer import emit_diagnostic

    sig = inspect.signature(emit_diagnostic)
    status_param = sig.parameters["status"]
    assert status_param.default == "info", (
        f"emit_diagnostic default status should be 'info' per G-14; got {status_param.default!r}"
    )


def test_tool_journal_call_sites_pass_explicit_status():
    """The 3 call sites in tool_journal.py pass explicit DiagnosticStatus."""
    source = Path("lca/cognition/body/emit/tool_journal.py").read_text()
    assert "DiagnosticStatus.STARTED.value" in source, (
        "record_tools_started_diagnostic must pass status=DiagnosticStatus.STARTED.value"
    )
    assert "DiagnosticStatus.FAILED.value" in source, (
        "record_tool_denied_observability must pass status=DiagnosticStatus.FAILED.value"
    )
    assert "DiagnosticStatus.SUCCEEDED.value" in source, (
        "record_tool_invoked_diagnostic must pass SUCCEEDED/FAILED based on obs.success"
    )


def test_perceive_hub_call_sites_pass_explicit_status():
    """The 2 call sites in perceive/hub.py pass explicit DiagnosticStatus.FAILED."""
    source = Path("lca/cognition/perceive/hub.py").read_text()
    count = source.count("status=DiagnosticStatus.FAILED.value")
    assert count >= 2, (
        f"perceive/hub.py should pass explicit FAILED at both sensor.read and "
        f"memory.perceive; found {count} instances"
    )
