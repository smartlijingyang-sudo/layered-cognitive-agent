"""Tests for :mod:`lca.harness.diagnostics.audit_state_writers`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.harness.diagnostics.audit_state_writers import (
    Finding,
    format_report,
    scan_state_writers,
)


@pytest.fixture
def layer_dir(tmp_path: Path) -> Path:
    """Create a fake layer directory for testing."""
    layer = tmp_path / "lca" / "layer1_cognitive"
    layer.mkdir(parents=True)
    return layer


def _write_py(directory: Path, name: str, source: str) -> Path:
    """Write a Python file with the given source code."""
    path = directory / name
    path.write_text(source, encoding="utf-8")
    return path


class TestScanStateWriters:
    """Tests for :func:`scan_state_writers`."""

    def test_detects_attr_assign(self, layer_dir: Path) -> None:
        """Pattern 1: ``state.x = 1`` should be detected."""
        source = """\
def update(state):
    state.x = 1
    state.y = 2
"""
        _write_py(layer_dir, "mod.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) >= 2
        kinds = {f.kind for f in findings}
        assert "direct_attr_assign" in kinds
        for finding in findings:
            assert finding.kind == "direct_attr_assign"
            assert finding.path.endswith("mod.py")

    def test_detects_self_state_attr_assign(self, layer_dir: Path) -> None:
        """Pattern 1: ``self.state.x = 1`` should be detected."""
        source = """\
class Handler:
    def update(self, state):
        self.state.x = 1
"""
        _write_py(layer_dir, "handler.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) >= 1
        assert findings[0].kind == "direct_attr_assign"
        assert "self.state.x" not in findings[0].message or "state.x" in findings[0].message

    def test_detects_subscript_assign(self, layer_dir: Path) -> None:
        """Pattern 3: ``state["k"] = 1`` should be detected."""
        source = """\
def update(state):
    state["k"] = 1
    self.state["m"] = 2
"""
        _write_py(layer_dir, "subscript.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) >= 2
        kinds = {f.kind for f in findings}
        assert "subscript_assign" in kinds
        for finding in findings:
            assert finding.kind == "subscript_assign"

    def test_detects_aug_assign(self, layer_dir: Path) -> None:
        """Pattern 2: ``state.x += 1`` should be detected."""
        source = """\
def update(state):
    state.x += 1
    state.y -= 2
"""
        _write_py(layer_dir, "aug.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) >= 2
        kinds = {f.kind for f in findings}
        assert "direct_attr_assign" in kinds
        for finding in findings:
            assert finding.kind == "direct_attr_assign"

    def test_detects_dict_update(self, layer_dir: Path) -> None:
        """Pattern 4: ``state.field.update(...)`` should be detected."""
        source = """\
def update(state):
    state.extra.update({"k": 1})
    state.history.extend([1, 2])
"""
        _write_py(layer_dir, "dict_update.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) >= 2
        kinds = {f.kind for f in findings}
        assert "dict_or_setattr_mutation" in kinds

    def test_detects_setattr_call(self, layer_dir: Path) -> None:
        """Pattern 4: ``setattr(state, ...)`` should be detected."""
        source = """\
def update(state):
    setattr(state, "x", 1)
"""
        _write_py(layer_dir, "setattr.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) >= 1
        assert findings[0].kind == "dict_or_setattr_mutation"

    def test_detects_method_call_mutation(self, layer_dir: Path) -> None:
        """Pattern 5: ``state.append(...)`` should be detected."""
        source = """\
def update(state):
    state.append(1)
    state.clear()
"""
        _write_py(layer_dir, "method.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) >= 2
        kinds = {f.kind for f in findings}
        assert "method_call_mutation" in kinds

    def test_clean_function_passes(self, layer_dir: Path) -> None:
        """A pure function with no state mutation should yield 0 findings."""
        source = """\
def pure(x, y):
    return x + y

def read_only(state):
    return state.x + state.y
"""
        _write_py(layer_dir, "clean.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) == 0

    def test_allowlisted_reducer_file_clean(self, tmp_path: Path) -> None:
        """Files matching the allowlist should be skipped."""
        # Create a file at the exact allowlisted path
        reducer_dir = tmp_path / "lca" / "layer2_runtime"
        reducer_dir.mkdir(parents=True)
        reducer_file = reducer_dir / "reducer.py"
        source = """\
class DefaultReducer:
    def apply_step(self, state, step):
        state.step = step
        state.budget.used_steps = step
        return state
"""
        reducer_file.write_text(source, encoding="utf-8")
        # Scan from tmp_path root — the allowlist should match
        findings = scan_state_writers([tmp_path])
        assert len(findings) == 0

    def test_nested_attr_chain_detected(self, layer_dir: Path) -> None:
        """``state.budget.used_steps = step`` should be detected."""
        source = """\
def update(state):
    state.budget.used_steps = 1
"""
        _write_py(layer_dir, "nested.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) >= 1
        assert findings[0].kind == "direct_attr_assign"

    def test_tuple_unpacking_detected(self, layer_dir: Path) -> None:
        """``state.x, state.y = 1, 2`` should detect both mutations."""
        source = """\
def update(state):
    state.x, state.y = 1, 2
"""
        _write_py(layer_dir, "unpack.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) >= 2
        for finding in findings:
            assert finding.kind == "direct_attr_assign"


class TestFormatReport:
    """Tests for :func:`format_report`."""

    def test_format_report_empty(self) -> None:
        """Empty findings list should produce a clean message."""
        report = format_report([])
        assert "No state mutations detected" in report
        assert report.endswith("\n")

    def test_format_report_text_mode(self) -> None:
        """Text mode should list findings with path:line:col."""
        findings = [
            Finding(
                path="lca/layer1_cognitive/mod.py",
                line=10,
                col=4,
                kind="direct_attr_assign",
                message="state.x = ... at line 10",
            )
        ]
        report = format_report(findings, json_mode=False)
        assert "Found 1 state mutation(s)" in report
        assert "lca/layer1_cognitive/mod.py:10:4" in report
        assert "direct_attr_assign" in report
        assert report.endswith("\n")

    def test_format_report_json(self) -> None:
        """JSON mode should produce valid JSON with expected keys."""
        findings = [
            Finding(
                path="lca/layer1_cognitive/mod.py",
                line=10,
                col=4,
                kind="direct_attr_assign",
                message="state.x = ... at line 10",
            ),
            Finding(
                path="lca/layer2_runtime/other.py",
                line=20,
                col=8,
                kind="subscript_assign",
                message="state[...] = ... at line 20",
            ),
        ]
        report = format_report(findings, json_mode=True)
        assert report.endswith("\n")
        # Parse and validate
        data = json.loads(report)
        assert isinstance(data, list)
        assert len(data) == 2
        # Each entry should have the expected keys
        expected_keys = {"path", "line", "col", "kind", "message"}
        for entry in data:
            assert set(entry.keys()) == expected_keys
        # Spot-check values
        assert data[0]["path"] == "lca/layer1_cognitive/mod.py"
        assert data[0]["line"] == 10
        assert data[0]["kind"] == "direct_attr_assign"
        assert data[1]["kind"] == "subscript_assign"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
