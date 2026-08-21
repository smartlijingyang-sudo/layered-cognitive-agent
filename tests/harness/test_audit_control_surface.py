"""Tests for Control Surface audit script."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.harness.diagnostics.audit_control_surface import (
    format_report,
    scan_control_surface,
)


class TestScanControlSurface:
    def test_detects_hardcoded_slot_in_python(self, tmp_path: Path) -> None:
        """Test that hardcoded Control Slot strings are detected in Python files."""
        py_file = tmp_path / "test_plugin.py"
        py_file.write_text(
            '''"""Test plugin with hardcoded slot."""


def setup() -> None:
    """Setup function."""
    slot_name = "perceive.context"
    return slot_name
''',
            encoding="utf-8",
        )

        findings = scan_control_surface([tmp_path])
        assert "perceive.context" in findings
        assert len(findings["perceive.context"]) == 1

        finding = findings["perceive.context"][0]
        assert finding.path == str(py_file)
        assert finding.kind == "hardcoded_slot_ref"
        assert finding.message == "perceive.context"
        assert finding.line == 6
        assert finding.col >= 0

    def test_missing_control_field_in_yaml(self, tmp_path: Path) -> None:
        """Test that YAML plugins without 'control' field are flagged."""
        yaml_file = tmp_path / "test_plugin.yaml"
        yaml_file.write_text(
            """id: test.plugin
provides:
  - test_service
setup: test_plugin.setup
""",
            encoding="utf-8",
        )

        findings = scan_control_surface([tmp_path])
        assert "__missing_control__" in findings
        assert len(findings["__missing_control__"]) == 1

        finding = findings["__missing_control__"][0]
        assert finding.path == str(yaml_file)
        assert finding.kind == "missing_control_field"
        assert "test.plugin" in finding.message
        assert "control:" in finding.message

    def test_clean_file_returns_empty(self, tmp_path: Path) -> None:
        """Test that clean files (no slots, valid YAML) return empty findings."""
        # Clean Python file with no slot references
        py_file = tmp_path / "clean.py"
        py_file.write_text(
            '''"""Clean module."""


def do_something() -> str:
    """Do something."""
    return "normal_string"
''',
            encoding="utf-8",
        )

        # Clean YAML with control field
        yaml_file = tmp_path / "clean.yaml"
        yaml_file.write_text(
            """id: clean.plugin
provides:
  - clean_service
control:
  slot: perceive.context
  policy: default
setup: clean.setup
""",
            encoding="utf-8",
        )

        findings = scan_control_surface([tmp_path])
        assert findings == {}

    def test_format_report_human_and_json(self, tmp_path: Path) -> None:
        """Test format_report produces valid output in both modes."""
        py_file = tmp_path / "test.py"
        py_file.write_text(
            '''"""Test."""

slot = "act.execute"
''',
            encoding="utf-8",
        )

        findings = scan_control_surface([tmp_path])
        assert len(findings) > 0

        # Test human-readable format
        human_report = format_report(findings, json_mode=False)
        assert isinstance(human_report, str)
        assert len(human_report) > 0
        assert "act.execute" in human_report
        assert "hardcoded_slot_ref" in human_report

        # Test JSON format
        json_report = format_report(findings, json_mode=True)
        assert isinstance(json_report, str)
        assert len(json_report) > 0

        # Verify it's valid JSON
        parsed = json.loads(json_report)
        assert isinstance(parsed, dict)
        assert "act.execute" in parsed
        assert isinstance(parsed["act.execute"], list)
        assert len(parsed["act.execute"]) == 1

        finding_dict = parsed["act.execute"][0]
        assert finding_dict["path"] == str(py_file)
        assert finding_dict["kind"] == "hardcoded_slot_ref"
        assert finding_dict["message"] == "act.execute"

    def test_multiple_slots_in_one_file(self, tmp_path: Path) -> None:
        """Test that multiple slots in one file are all detected."""
        py_file = tmp_path / "multi.py"
        py_file.write_text(
            '''"""Multiple slots."""

slots = ["perceive.context", "think.guard", "act.execute"]
''',
            encoding="utf-8",
        )

        findings = scan_control_surface([tmp_path])
        assert "perceive.context" in findings
        assert "think.guard" in findings
        assert "act.execute" in findings
        assert len(findings["perceive.context"]) == 1
        assert len(findings["think.guard"]) == 1
        assert len(findings["act.execute"]) == 1

    def test_nested_yaml_structure(self, tmp_path: Path) -> None:
        """Test YAML scanning with nested plugin structure."""
        yaml_file = tmp_path / "nested.yaml"
        yaml_file.write_text(
            """---
id: plugin.one
provides:
  - service_a

---
id: plugin.two
provides:
  - service_b
control:
  slot: think.guard

---
id: plugin.three
provides:
  - service_c
""",
            encoding="utf-8",
        )

        findings = scan_control_surface([tmp_path])
        assert "__missing_control__" in findings
        # plugin.one and plugin.three are missing control
        assert len(findings["__missing_control__"]) == 2

        messages = [f.message for f in findings["__missing_control__"]]
        assert any("plugin.one" in msg for msg in messages)
        assert any("plugin.three" in msg for msg in messages)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
