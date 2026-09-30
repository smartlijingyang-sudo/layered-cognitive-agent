"""Structural tests: the assistant tool-filter alias is gone.

``filter_tools_by_assistant`` lives in ``lca.infrastructure.tools.assistant.filter``;
the `lca.plugins.assistant.tools` re-export alias had no production consumers and
was deleted. Tests and production code must import the concrete module.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_alias_module_is_deleted() -> None:
    assert not (REPO / "lca" / "plugins" / "assistant" / "tools.py").exists()


def test_filter_tools_imports_from_concrete_module() -> None:
    from lca.infrastructure.tools.assistant.filter import filter_tools_by_assistant

    assert callable(filter_tools_by_assistant)


def test_no_production_module_imports_alias() -> None:
    import re

    violations: list[str] = []
    for path in (REPO / "lca").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(
            r"(from lca\.plugins\.assistant\.tools import|import lca\.plugins\.assistant\.tools)",
            text,
        ):
            violations.append(str(path))
    assert violations == [], f"alias still imported by: {violations}"


def test_filter_test_lives_next_to_implementation() -> None:
    assert (
        REPO / "tests" / "infrastructure" / "tools" / "assistant" / "test_filter_tools.py"
    ).exists()
    assert not (REPO / "tests" / "plugins" / "assistant" / "test_filter_tools.py").exists()
