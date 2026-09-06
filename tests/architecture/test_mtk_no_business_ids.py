"""ADR-0194 L6 — MTK must not embed business plugin ids."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LCA = ROOT / "lca"

MTK_ROOTS = (
    LCA / "harness" / "graph",
    LCA / "loop" / "driver.py",
    LCA / "loop" / "transaction.py",
    LCA / "loop" / "emit" / "spine" / "phase_fact.py",
)

# Concrete bundle/profile plugin ids and tool brands — MTK uses capability prefixes only.
FORBIDDEN_LITERAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "phase executor plugin id",
        re.compile(
            r"""['"]phase\.(perceive|think|act|reflect|remember|stop)\.[a-z][a-z0-9_.-]*['"]"""
        ),
    ),
    (
        "control contribution plugin id",
        re.compile(r"""['"]control\.(think|act|stop)\.[a-z][a-z0-9_.-]*['"]"""),
    ),
    (
        "plugins module path",
        re.compile(r"""['"]lca\.plugins\.[a-z][a-z0-9_.-]*['"]"""),
    ),
)

ALLOWLIST_SUBSTRINGS = (
    "phase.topology.",
    "phase.edge.",
    "phase.execution_policy.",
    "control.denied",
    "control.exhausted",
    "control.stopped",
    "control.paused",
    "control.rewrite_requested",
)


def _mtk_python_files() -> list[Path]:
    files: list[Path] = []
    for root in MTK_ROOTS:
        if root.is_file():
            files.append(root)
            continue
        if not root.is_dir():
            pytest.skip(f"MTK root missing: {root}")
        files.extend(sorted(root.rglob("*.py")))
    return files


def test_mtk_no_business_ids() -> None:
    """Graph/loop mechanism must not hard-code profile-selected plugin identities."""
    offenders: list[str] = []
    for path in _mtk_python_files():
        text = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN_LITERAL_PATTERNS:
            for match in pattern.finditer(text):
                snippet = match.group(0)
                if any(token in snippet for token in ALLOWLIST_SUBSTRINGS):
                    continue
                rel = path.relative_to(ROOT)
                offenders.append(f"{rel}: {label} → {snippet}")
    assert not offenders, "MTK business plugin id literals found:\n" + "\n".join(offenders)
