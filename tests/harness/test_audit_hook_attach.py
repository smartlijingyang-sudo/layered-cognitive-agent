"""Tests for ``lca.harness.diagnostics.audit_hook_attach`` (PR-0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.harness.diagnostics.audit_hook_attach import (
    Finding,
    format_report,
    scan_hook_attach,
)


def _write_py(path: Path, source: str) -> Path:
    """Write a Python file with the given source and return its path."""
    path.write_text(source, encoding="utf-8")
    return path


class TestScanHookAttach:
    """Test suite for scan_hook_attach()."""

    def test_detects_hooks_trigger_call(self, tmp_path: Path) -> None:
        """``hooks.trigger("x", cb)`` must be flagged."""
        root = tmp_path / "layer1_cognitive"
        root.mkdir()
        _write_py(root / "some_module.py", 'hooks.trigger("x", cb)\n')

        findings = scan_hook_attach([root])

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "hooks_trigger_call"
        assert f.message == "hooks.trigger"
        assert "some_module.py" in f.path
        assert f.line == 1

    def test_detects_middleware_bag_attr(self, tmp_path: Path) -> None:
        """``middleware_bag.append(x)`` must be flagged."""
        root = tmp_path / "layer2_runtime"
        root.mkdir()
        _write_py(root / "runtime_core.py", "middleware_bag.append(x)\n")

        findings = scan_hook_attach([root])

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "middleware_bag_attr"
        assert f.message == "middleware_bag.append"
        assert "runtime_core.py" in f.path

    def test_detects_underscore_emit_call(self, tmp_path: Path) -> None:
        """``self._emit(event)`` must be flagged (call to _emit)."""
        root = tmp_path / "layer3_agent"
        root.mkdir()
        _write_py(
            root / "agent.py",
            "class Agent:\n    def run(self):\n        self._emit(event)\n",
        )

        findings = scan_hook_attach([root])

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "legacy_underscore_emit"
        assert f.message == "_emit"

    def test_skips_underscore_emit_assign_target(self, tmp_path: Path) -> None:
        """``self._emit = {}`` must NOT be flagged (assign target)."""
        root = tmp_path / "layer4_app"
        root.mkdir()
        _write_py(
            root / "composer.py",
            "class Composer:\n    def __init__(self):\n        self._emit = {}\n",
        )

        findings = scan_hook_attach([root])

        assert len(findings) == 0

    def test_allowlist_event_bus_clean(self, tmp_path: Path) -> None:
        """Files named ``event_bus.py`` or ``hook_registry.py`` must be skipped."""
        root = tmp_path / "layer1_cognitive"
        root.mkdir()
        # event_bus.py legitimately holds _emit
        _write_py(
            root / "event_bus.py",
            "class EventBus:\n    def _emit(self, event):\n        pass\n",
        )
        # hook_registry.py legitimately holds middleware_bag
        _write_py(
            root / "hook_registry.py",
            "class HookRegistry:\n    middleware_bag = []\n",
        )

        findings = scan_hook_attach([root])

        assert len(findings) == 0

    def test_detects_register_hook_call(self, tmp_path: Path) -> None:
        """``register_hook(...)`` as a bare call must be flagged."""
        root = tmp_path / "layer1_cognitive"
        root.mkdir()
        _write_py(root / "hooks_user.py", "register_hook('on_start', callback)\n")

        findings = scan_hook_attach([root])

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "legacy_hook_attach"
        assert f.message == "register_hook"

    def test_detects_obj_register_hook_call(self, tmp_path: Path) -> None:
        """``obj.register_hook(...)`` as a method call must be flagged."""
        root = tmp_path / "layer2_runtime"
        root.mkdir()
        _write_py(root / "runtime.py", "runtime.register_hook('on_start', callback)\n")

        findings = scan_hook_attach([root])

        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "legacy_hook_attach"
        assert f.message == "register_hook"

    def test_detects_attach_hook_call(self, tmp_path: Path) -> None:
        """``attach_hook(...)`` must be flagged."""
        root = tmp_path / "layer3_agent"
        root.mkdir()
        _write_py(root / "agent.py", "attach_hook('pre_think', handler)\n")

        findings = scan_hook_attach([root])

        assert len(findings) == 1
        assert findings[0].kind == "legacy_hook_attach"
        assert findings[0].message == "attach_hook"

    def test_detects_subscribe_call(self, tmp_path: Path) -> None:
        """``subscribe(...)`` must be flagged."""
        root = tmp_path / "layer4_app"
        root.mkdir()
        _write_py(root / "composer.py", "bus.subscribe('event', handler)\n")

        findings = scan_hook_attach([root])

        assert len(findings) == 1
        assert findings[0].kind == "legacy_hook_attach"
        assert findings[0].message == "subscribe"

    def test_skips_syntax_error_file(self, tmp_path: Path) -> None:
        """Files with syntax errors must be skipped gracefully."""
        root = tmp_path / "layer1_cognitive"
        root.mkdir()
        _write_py(root / "broken.py", "def foo(:\n")

        findings = scan_hook_attach([root])

        assert len(findings) == 0

    def test_nonexistent_root_skipped(self, tmp_path: Path) -> None:
        """Non-existent roots must be skipped without error."""
        findings = scan_hook_attach([tmp_path / "does_not_exist"])
        assert len(findings) == 0

    def test_multiple_patterns_in_one_file(self, tmp_path: Path) -> None:
        """Multiple patterns in one file must all be detected."""
        root = tmp_path / "layer1_cognitive"
        root.mkdir()
        source = (
            "hooks.trigger('x', cb)\n"
            "middleware_bag.append(x)\n"
            "self._emit(event)\n"
            "register_hook('on_start', handler)\n"
        )
        _write_py(root / "multi.py", source)

        findings = scan_hook_attach([root])

        kinds = {f.kind for f in findings}
        assert "hooks_trigger_call" in kinds
        assert "middleware_bag_attr" in kinds
        assert "legacy_underscore_emit" in kinds
        assert "legacy_hook_attach" in kinds


class TestFormatReport:
    """Test suite for format_report()."""

    def test_format_report_empty(self) -> None:
        """Empty findings list must produce a clean message."""
        report = format_report([])
        assert "no residual" in report.lower() or "✓" in report

    def test_format_report_json(self) -> None:
        """JSON mode must produce valid JSON with expected shape."""
        findings = [
            Finding(
                path="test.py",
                line=10,
                col=5,
                kind="hooks_trigger_call",
                message="hooks.trigger",
            )
        ]
        report = format_report(findings, json_mode=True)
        data = json.loads(report)

        assert isinstance(data, list)
        assert len(data) == 1
        item = data[0]
        assert item["path"] == "test.py"
        assert item["line"] == 10
        assert item["col"] == 5
        assert item["kind"] == "hooks_trigger_call"
        assert item["message"] == "hooks.trigger"

    def test_format_report_text(self) -> None:
        """Text mode must produce human-readable output."""
        findings = [
            Finding(
                path="test.py",
                line=10,
                col=5,
                kind="hooks_trigger_call",
                message="hooks.trigger",
            )
        ]
        report = format_report(findings, json_mode=False)

        assert "1 residual" in report
        assert "hooks_trigger_call" in report
        assert "test.py:10:5" in report
        assert "hooks.trigger" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
