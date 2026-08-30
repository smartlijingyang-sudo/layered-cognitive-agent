"""Tests for :mod:`lca.harness.diagnostics.audit_direct_commands`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.harness.diagnostics.audit_direct_commands import (
    format_report,
    scan_direct_commands,
)


class TestScanDirectCommands:
    """Behavioural tests for the Body audit scanner."""

    def test_detects_layer0_transport_import(self, tmp_path: Path) -> None:
        """``from lca.infrastructure.transport.X import Y`` is flagged."""
        py_file = tmp_path / "bad_transport_user.py"
        py_file.write_text(
            '"""Module that reaches L0 transport directly."""\n'
            "\n"
            "from lca.infrastructure.transport.ssh import connect\n"
            "\n"
            "def open_channel(host: str) -> object:\n"
            "    return connect(host)\n",
            encoding="utf-8",
        )

        findings = scan_direct_commands([tmp_path])
        assert len(findings) == 1, f"expected exactly 1 finding, got {findings!r}"

        (finding,) = findings
        assert finding.path == str(py_file)
        assert finding.line == 3
        assert finding.col == 0
        assert finding.kind == "direct_layer0_import"
        assert "lca.infrastructure.transport.ssh" in finding.message
        assert "connect" in finding.message

    def test_detects_layer0_sandbox_import_alias(self, tmp_path: Path) -> None:
        """``import lca.infrastructure.sandbox as sb`` is flagged as an import.

        Aliased calls like ``sb.run(...)`` are not flagged as direct calls
        (only bare ``sandbox.run`` is), but the import itself is caught.
        """
        py_file = tmp_path / "bare_import.py"
        py_file.write_text(
            '"""Module with a bare L0 sandbox import."""\n'
            "\n"
            "import lca.infrastructure.sandbox as sb\n"
            "\n"
            "def run_cmd(cmd: str) -> str:\n"
            "    return sb.run(cmd)\n",
            encoding="utf-8",
        )

        findings = scan_direct_commands([tmp_path])
        # The import is flagged; the aliased call is not (correct behavior).
        assert len(findings) == 1
        (finding,) = findings
        assert finding.kind == "direct_layer0_import"
        assert "lca.infrastructure.sandbox" in finding.message

    def test_detects_sandbox_call(self, tmp_path: Path) -> None:
        """``sandbox.run(...)`` is flagged even without a direct import."""
        py_file = tmp_path / "caller.py"
        py_file.write_text(
            '"""Caller that uses the bare sandbox name."""\n'
            "\n"
            "def do_it() -> None:\n"
            "    sandbox.run('ls -la')\n",
            encoding="utf-8",
        )

        findings = scan_direct_commands([tmp_path])
        assert len(findings) == 1
        (finding,) = findings
        assert finding.path == str(py_file)
        assert finding.line == 4
        assert finding.kind == "direct_sandbox_call"
        assert finding.message == "sandbox.run"

    def test_detects_transport_call(self, tmp_path: Path) -> None:
        """``transport.send(...)`` is flagged as a direct transport call."""
        py_file = tmp_path / "sender.py"
        py_file.write_text(
            '"""Sender that uses the bare transport name."""\n'
            "\n"
            "def ship(payload: bytes) -> None:\n"
            "    transport.send(payload)\n",
            encoding="utf-8",
        )

        findings = scan_direct_commands([tmp_path])
        assert len(findings) == 1
        (finding,) = findings
        assert finding.kind == "direct_transport_call"
        assert finding.message == "transport.send"

    def test_clean_body_file_passes(self, tmp_path: Path) -> None:
        """A file that only uses SafeExecutor / ActionRegistry is clean."""
        py_file = tmp_path / "clean_body.py"
        py_file.write_text(
            '"""A well-behaved Body module."""\n'
            "\n"
            "from lca.cognition.body import ActionRegistry, SafeExecutor\n"
            "from lca.cognition.body.action_registry import ActionDescriptor\n"
            "\n"
            "\n"
            "def register_ping(registry: ActionRegistry) -> None:\n"
            "    descriptor = ActionDescriptor(name='ping', handler=lambda ctx: 'pong')\n"
            "    registry.register(descriptor)\n"
            "\n"
            "\n"
            "def run_safely(executor: SafeExecutor, action: str) -> object:\n"
            "    return executor.execute(action)\n",
            encoding="utf-8",
        )

        findings = scan_direct_commands([tmp_path])
        assert findings == [], f"expected no findings, got {findings!r}"

    def test_method_on_local_sandbox_is_not_flagged(self, tmp_path: Path) -> None:
        """``self.sandbox.run(...)`` is *not* a direct command — it is seam usage."""
        py_file = tmp_path / "seam_user.py"
        py_file.write_text(
            '"""Module that uses a seam-injected sandbox."""\n'
            "\n"
            "class Body:\n"
            "    def __init__(self, sandbox) -> None:\n"
            "        self.sandbox = sandbox\n"
            "\n"
            "    def act(self, cmd: str) -> str:\n"
            "        return self.sandbox.run(cmd)\n",
            encoding="utf-8",
        )

        findings = scan_direct_commands([tmp_path])
        assert findings == []

    def test_nonexistent_root_is_ignored(self, tmp_path: Path) -> None:
        """Missing roots do not raise — they contribute no findings."""
        missing = tmp_path / "does_not_exist"
        findings = scan_direct_commands([missing])
        assert findings == []

    def test_unparsable_file_is_skipped(self, tmp_path: Path) -> None:
        """Syntax errors are silently skipped (audit reports what it can)."""
        py_file = tmp_path / "broken.py"
        py_file.write_text(
            "def oops(:\n    return\n",
            encoding="utf-8",
        )
        findings = scan_direct_commands([tmp_path])
        assert findings == []

    def test_findings_are_sorted(self, tmp_path: Path) -> None:
        """Output is sorted by (path, line, col) for stable reports."""
        py_file = tmp_path / "multi.py"
        py_file.write_text(
            '"""Multiple violations in one file."""\n'
            "\n"
            "import lca.infrastructure.sandbox\n"
            "from lca.infrastructure.transport.ssh import connect\n"
            "\n"
            "def go() -> None:\n"
            "    sandbox.run('x')\n"
            "    transport.send(b'y')\n",
            encoding="utf-8",
        )
        findings = scan_direct_commands([tmp_path])
        assert len(findings) == 4
        ordered = sorted(findings, key=lambda f: (f.path, f.line, f.col))
        assert findings == ordered


class TestFormatReport:
    """Behavioural tests for :func:`format_report`."""

    def test_format_report_json(self, tmp_path: Path) -> None:
        """JSON mode produces a list of dicts with the Finding fields."""
        py_file = tmp_path / "sample.py"
        py_file.write_text(
            '"""Sample."""\n\nsandbox.run(\'ls\')\n',
            encoding="utf-8",
        )
        findings = scan_direct_commands([tmp_path])
        assert findings, "precondition: scanner must produce findings"

        report = format_report(findings, json_mode=True)
        parsed = json.loads(report)
        assert isinstance(parsed, list)
        assert len(parsed) == len(findings)

        entry = parsed[0]
        assert isinstance(entry, dict)
        for key in ("path", "line", "col", "kind", "message"):
            assert key in entry, f"missing key {key!r} in JSON output"
        assert entry["kind"] == "direct_sandbox_call"
        assert entry["message"] == "sandbox.run"
        assert entry["path"] == str(py_file)

    def test_format_report_human(self, tmp_path: Path) -> None:
        """Human mode mentions the path + kind + message."""
        py_file = tmp_path / "sample.py"
        py_file.write_text(
            '"""Sample."""\n\ntransport.send(b\'x\')\n',
            encoding="utf-8",
        )
        findings = scan_direct_commands([tmp_path])
        report = format_report(findings, json_mode=False)
        assert str(py_file) in report
        assert "direct_transport_call" in report
        assert "transport.send" in report

    def test_format_report_empty(self) -> None:
        """Empty findings produce a clean-success banner."""
        report = format_report([], json_mode=False)
        assert "No direct" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
