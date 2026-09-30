"""Structural tests: the COMPAT spine sink plugins migrated.

The old ``lca.plugins.observability.spine.sinks`` package (file/console sink
plugins) moved to ``lca.plugins.events.sinks.{file_sink,console_sink}``; the
COMPAT delete-when condition has landed.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_old_sinks_package_is_gone() -> None:
    old_pkg = REPO / "lca" / "plugins" / "observability" / "spine" / "sinks"
    assert not old_pkg.exists()


def test_new_sink_plugins_import_cleanly() -> None:
    from lca.plugins.events.sinks.console_sink import ConsoleSink
    from lca.plugins.events.sinks.console_sink import setup as console_setup
    from lca.plugins.events.sinks.file_sink import setup as file_setup

    assert hasattr(console_setup, "setup")
    assert hasattr(file_setup, "setup")
    assert ConsoleSink is not None


def test_bundles_reference_new_sink_paths() -> None:
    for bundle in (
        "bundles/loop_cursor.spine_default.yaml",
        "bundles/loop_cursor.spine_minimal.yaml",
    ):
        text = (REPO / bundle).read_text(encoding="utf-8")
        assert "lca.plugins.events.sinks.file_sink" in text
        assert "lca.plugins.observability.spine.sinks" not in text


def test_no_production_reference_to_old_sinks_path() -> None:
    violations: list[str] = []
    for path in (REPO / "lca").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"lca\.plugins\.observability\.spine\.sinks", text):
            violations.append(str(path))
    assert violations == [], f"old sinks path still referenced: {violations}"
