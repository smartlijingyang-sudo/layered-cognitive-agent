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


def test_session_setup_coordinator_does_not_own_builder_or_diagnostics() -> None:
    """The setup facade coordinates distinct ownership modules."""
    setup = ROOT / "gateway" / "runs" / "session_setup.py"
    source = setup.read_text(encoding="utf-8")

    assert "RunSessionBuilder" in source
    assert "RunBootSnapshotRecorder" in source
    assert "record_runtime" not in source
    assert "create_run_components" not in source


def test_session_builder_does_not_publish_or_emit_diagnostics() -> None:
    """The builder owns assembly only, not publication or observability writes."""
    builder = ROOT / "gateway" / "runs" / "session_builder.py"
    imports = _imports(builder)
    source = builder.read_text(encoding="utf-8")

    assert "registry.put" not in source
    assert "record_runtime" not in source
    assert "lca.layer0_infra.observability" not in imports
