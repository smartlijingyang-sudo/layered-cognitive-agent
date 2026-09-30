"""Structural tests: known-retired module paths must not be referenced.

The LCA codebase has retired several module paths during the kernel cutover
(ADR-0181/0195). Live Python code must not import or read them; historical
docs/notes may still mention them. Plugin-ID strings that merely share a
namespace prefix (e.g. ``lca.plugins.assistant.tools.tools``) are legitimate
and are not flagged.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: (dotted path, file path) pairs fully retired from the live tree.
_RETIRED_PATHS: tuple[tuple[str, str], ...] = (
    ("lca.loop.transaction", "lca/loop/transaction.py"),
    ("lca.harness.graph.execute.interpreter", "lca/harness/graph/execute/interpreter.py"),
    ("lca.runtime.runtime_loop", "lca/runtime/runtime_loop.py"),
    ("lca.harness.profile.boot.boot", "lca/harness/profile/boot/boot.py"),
    ("lca.plugins.assistant.tools", "lca/plugins/assistant/tools.py"),
)


def _live_python_files() -> list[Path]:
    files: list[Path] = []
    # Scan production code and scripts only; tests may legitimately assert
    # that a retired path no longer exists.
    for root in ("lca", "lca_kernel", "scripts"):
        for path in (REPO / root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def test_no_live_reference_to_retired_paths() -> None:
    violations: list[str] = []
    for path in _live_python_files():
        text = path.read_text(encoding="utf-8")
        for dotted, rel in _RETIRED_PATHS:
            # Import statements (`import X` / `from X import ...`).
            if re.search(rf"(?:from|import)\s+{re.escape(dotted)}\b", text):
                violations.append(f"{path}: import {dotted}")
            # File reads (`Path("lca/loop/transaction.py")` style).
            if re.search(rf'["\']{re.escape(rel)}["\']', text):
                violations.append(f"{path}: read {rel}")
    assert violations == [], f"retired module paths referenced: {violations}"


def test_retired_files_do_not_exist() -> None:
    for _, rel in _RETIRED_PATHS:
        assert not (REPO / rel).exists(), f"retired module still exists: {rel}"
