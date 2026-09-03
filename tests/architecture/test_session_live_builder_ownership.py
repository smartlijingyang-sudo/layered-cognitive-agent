"""Session Spine provider ownership and dependency direction invariants."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_session_live_builder_is_owned_by_application() -> None:
    """The session live builder provider is pluginized under ``lca.plugins.runtime``."""
    provider = ROOT / "lca" / "plugins" / "runtime" / "session_live_builder.py"
    legacy = ROOT / "lca" / "application" / "session_live_builder_provider.py"

    assert provider.is_file()
    assert not legacy.exists()
    assert "lca.application.harness_bridge" in _imports(provider)


def test_plugins_do_not_import_session_live_bridge() -> None:
    """Plugin discovery must not pull an application-owned bridge into plugins.

    The exception is the session-live-builder provider itself (PR-9): it is the
    pluginized carrier of the bridge and must retain its import to materialize
    the live agent from durable session facts.
    """
    provider = ROOT / "lca" / "plugins" / "runtime" / "session_live_builder.py"
    for path in (ROOT / "lca" / "plugins").rglob("*.py"):
        if path == provider:
            continue
        assert "lca.application.harness_bridge" not in _imports(path), path
