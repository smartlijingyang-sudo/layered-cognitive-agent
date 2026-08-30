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
    path = directory / name
    path.write_text(source, encoding="utf-8")
    return path


class TestScanStateWriters:
    """The audit identifies writes to typed ``AgentState`` values only."""

    def test_detects_attr_assign(self, layer_dir: Path) -> None:
        source = """\
def update(state: AgentState):
    state.x = 1
    state.y = 2
"""
        _write_py(layer_dir, "mod.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) == 2
        assert {finding.kind for finding in findings} == {"direct_attr_assign"}

    def test_detects_self_state_attr_assign(self, layer_dir: Path) -> None:
        source = """\
class Handler:
    def update(self):
        self.state.x = 1
"""
        _write_py(layer_dir, "handler.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) == 1
        assert findings[0].kind == "direct_attr_assign"

    def test_detects_subscript_assign(self, layer_dir: Path) -> None:
        source = """\
def update(state: AgentState):
    state["k"] = 1
    self.state["m"] = 2
"""
        _write_py(layer_dir, "subscript.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) == 2
        assert {finding.kind for finding in findings} == {"subscript_assign"}

    def test_detects_aug_assign(self, layer_dir: Path) -> None:
        source = """\
def update(state: AgentState):
    state.x += 1
    state.y -= 2
"""
        _write_py(layer_dir, "aug.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) == 2
        assert {finding.kind for finding in findings} == {"direct_attr_assign"}

    def test_detects_mutating_container_methods(self, layer_dir: Path) -> None:
        source = """\
def update(state: AgentState):
    state.extra.update({"k": 1})
    state.history.extend([1, 2])
    state.clear()
"""
        _write_py(layer_dir, "mutate.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) == 3
        assert {finding.kind for finding in findings} == {
            "dict_or_setattr_mutation",
            "method_call_mutation",
        }

    def test_detects_setattr_call(self, layer_dir: Path) -> None:
        source = """\
def update(state: AgentState):
    setattr(state, "x", 1)
"""
        _write_py(layer_dir, "setattr.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) == 1
        assert findings[0].kind == "dict_or_setattr_mutation"

    def test_ignores_local_dict_named_state(self, layer_dir: Path) -> None:
        source = """\
def build() -> dict[str, object]:
    state: dict[str, object] = {}
    state["success"] = True
    state.setdefault("source", "agent")
    return state
"""
        _write_py(layer_dir, "local_dict.py", source)
        assert scan_state_writers([layer_dir]) == []

    def test_ignores_read_only_agent_state_methods(self, layer_dir: Path) -> None:
        source = """\
def inspect(state: AgentState) -> bool:
    return state.extra.get("flag", False) and state.budget.exceeded()

def snapshot(state: AgentState):
    return state.snapshot()
"""
        _write_py(layer_dir, "read_only.py", source)
        assert scan_state_writers([layer_dir]) == []

    def test_clean_function_passes(self, layer_dir: Path) -> None:
        source = """\
def pure(x, y):
    return x + y

def read_only(state: AgentState):
    return state.x + state.y
"""
        _write_py(layer_dir, "clean.py", source)
        assert scan_state_writers([layer_dir]) == []

    def test_allowlisted_reducer_file_clean(self, tmp_path: Path) -> None:
        reducer_dir = tmp_path / "lca" / "layer2_runtime"
        reducer_dir.mkdir(parents=True)
        reducer_file = reducer_dir / "reducer.py"
        reducer_file.write_text(
            """\
class DefaultReducer:
    def apply_step(self, state: AgentState, step):
        state.step = step
        state.budget.used_steps = step
        return state
""",
            encoding="utf-8",
        )
        assert scan_state_writers([tmp_path]) == []

    def test_nested_attr_chain_detected(self, layer_dir: Path) -> None:
        source = """\
def update(state: AgentState):
    state.budget.used_steps = 1
"""
        _write_py(layer_dir, "nested.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) == 1
        assert findings[0].kind == "direct_attr_assign"

    def test_tuple_unpacking_detected(self, layer_dir: Path) -> None:
        source = """\
def update(state: AgentState):
    state.x, state.y = 1, 2
"""
        _write_py(layer_dir, "unpack.py", source)
        findings = scan_state_writers([layer_dir])
        assert len(findings) == 2
        assert {finding.kind for finding in findings} == {"direct_attr_assign"}


class TestFormatReport:
    """Text and JSON rendering remains stable for CLI consumers."""

    def test_format_report_empty(self) -> None:
        report = format_report([])
        assert "No state mutations detected" in report
        assert report.endswith("\n")

    def test_format_report_text_mode(self) -> None:
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
        data = json.loads(report)
        assert isinstance(data, list)
        assert len(data) == 2
        expected_keys = {"path", "line", "col", "kind", "message"}
        for entry in data:
            assert set(entry.keys()) == expected_keys
        assert data[0]["path"] == "lca/layer1_cognitive/mod.py"
        assert data[0]["line"] == 10
        assert data[0]["kind"] == "direct_attr_assign"
        assert data[1]["kind"] == "subscript_assign"
