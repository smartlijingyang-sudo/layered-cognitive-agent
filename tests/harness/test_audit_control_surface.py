"""Tests for the declarative control-surface audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.harness.diagnostics.audit_control_surface import (
    format_report,
    scan_control_surface,
)

_RETIRED_KEY = "__retired_control_metadata__"


class TestScanControlSurface:
    def test_inventories_declarative_control_contribution(self, tmp_path: Path) -> None:
        py_file = tmp_path / "control_plugin.py"
        py_file.write_text(
            "PhaseContribution(executor='control.perceive.context')\n",
            encoding="utf-8",
        )

        findings = scan_control_surface([tmp_path])

        assert "control.perceive.context" in findings
        finding = findings["control.perceive.context"][0]
        assert finding.path == str(py_file)
        assert finding.kind == "declarative_control_contribution"
        assert finding.message == "control.perceive.context"
        assert finding.line == 1

    def test_ignores_non_control_contribution(self, tmp_path: Path) -> None:
        py_file = tmp_path / "ordinary_plugin.py"
        py_file.write_text(
            "PhaseContribution(executor='phase.think.default')\n",
            encoding="utf-8",
        )

        assert scan_control_surface([tmp_path]) == {}

    def test_yaml_without_retired_control_field_is_clean(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "plugin.yaml"
        yaml_file.write_text(
            "id: test.plugin\nprovides:\n  - test_service\nsetup: test_plugin.setup\n",
            encoding="utf-8",
        )

        assert scan_control_surface([tmp_path]) == {}

    def test_raw_control_field_in_yaml_is_flagged(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "legacy_plugin.yaml"
        yaml_file.write_text(
            "id: test.plugin\ncontrol:\n  slot: perceive.context\n",
            encoding="utf-8",
        )

        findings = scan_control_surface([tmp_path])

        assert _RETIRED_KEY in findings
        finding = findings[_RETIRED_KEY][0]
        assert finding.path == str(yaml_file)
        assert finding.kind == "retired_control_metadata"
        assert "retired" in finding.message

    def test_clean_files_return_empty(self, tmp_path: Path) -> None:
        (tmp_path / "clean.py").write_text(
            '"""Clean module."""\n\ndef do_something() -> str:\n    return "normal_string"\n',
            encoding="utf-8",
        )
        (tmp_path / "clean.yaml").write_text(
            "id: clean.plugin\nprovides:\n  - clean_service\nsetup: clean.setup\n",
            encoding="utf-8",
        )

        assert scan_control_surface([tmp_path]) == {}

    def test_format_report_human_and_json(self, tmp_path: Path) -> None:
        py_file = tmp_path / "legacy.py"
        py_file.write_text("plugin(control=legacy_control)\n", encoding="utf-8")

        findings = scan_control_surface([tmp_path])
        assert _RETIRED_KEY in findings

        human_report = format_report(findings, json_mode=False)
        assert "retired control metadata" in human_report
        assert str(py_file) in human_report

        json_report = format_report(findings, json_mode=True)
        parsed = json.loads(json_report)
        assert parsed[_RETIRED_KEY][0]["path"] == str(py_file)
        assert parsed[_RETIRED_KEY][0]["kind"] == "retired_control_metadata"

    def test_multiple_contributions_in_one_file(self, tmp_path: Path) -> None:
        py_file = tmp_path / "multi.py"
        py_file.write_text(
            "PhaseContribution(executor='control.perceive.context')\n"
            "PhaseContribution(executor='control.think.guard')\n"
            "PhaseContribution(executor='control.act.execute')\n",
            encoding="utf-8",
        )

        findings = scan_control_surface([tmp_path])

        assert set(findings) == {
            "control.perceive.context",
            "control.think.guard",
            "control.act.execute",
        }

    def test_multiple_raw_control_yaml_documents_are_flagged(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "nested.yaml"
        yaml_file.write_text(
            "---\nid: plugin.one\ncontrol: {}\n"
            "---\nid: plugin.two\ncontrol:\n  slot: think.guard\n"
            "---\nid: plugin.three\nprovides:\n  - service_c\n",
            encoding="utf-8",
        )

        findings = scan_control_surface([tmp_path])

        assert len(findings[_RETIRED_KEY]) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
