"""Tests for the standing-file assembly module.

Covers ``assemble_standing``, ``render_injected``, ``rehydrate_after_compaction``
and the fixed ``STANDING_ORDER``. The module lives in infrastructure so both
the memory refresh loader and the persona plugin depend on it without an upward
``infrastructure -> cognition`` import.
"""

from __future__ import annotations

import importlib

from lca.infrastructure.memory.contextfiles.domain.standing import (
    STANDING_ORDER,
    assemble_standing,
    rehydrate_after_compaction,
    render_injected,
)


def test_standing_order_has_five_fixed_files() -> None:
    assert STANDING_ORDER == ("SOUL.md", "USER.md", "MEMORY.md", "AGENTS.md", "TOOLS.md")


def test_assemble_standing_respects_budget() -> None:
    files = [("SOUL.md", "s" * 500), ("USER.md", "u" * 500), ("AGENTS.md", "a" * 500)]
    out = assemble_standing(files, budget_chars=100)
    assert len(out) <= 100


def test_assemble_standing_preserves_order() -> None:
    files = [("AGENTS.md", "agents"), ("SOUL.md", "soul"), ("USER.md", "user")]
    out = assemble_standing(files, budget_chars=1000)
    assert out.index("soul") < out.index("user") < out.index("agents")


def test_assemble_standing_empty_budget() -> None:
    assert assemble_standing([("SOUL.md", "x")], budget_chars=0) == ""


def test_assemble_standing_omits_blank_files() -> None:
    out = assemble_standing([("SOUL.md", "  "), ("USER.md", "user")], budget_chars=1000)
    assert "user" in out
    assert "soul" not in out.lower()


def test_assemble_standing_missing_file_treated_as_empty() -> None:
    out = assemble_standing([("SOUL.md", "soul")], budget_chars=1000)
    assert "soul" in out


def test_render_injected_wraps_body() -> None:
    rendered = render_injected("SOUL.md", "  body text  ")
    assert "<!-- INJECTED FILE: SOUL.md -->" in rendered
    assert "body text" in rendered
    assert "<!-- END INJECTED FILE: SOUL.md -->" in rendered


def test_rehydrate_after_compaction_keeps_history_then_standing() -> None:
    history = "old history line"
    files = [("SOUL.md", "fresh soul"), ("USER.md", "fresh user")]
    out = rehydrate_after_compaction(history, files, budget_chars=2000)
    assert "old history line" in out
    assert "fresh soul" in out


def test_rehydrate_after_compaction_budget_limits() -> None:
    history = "h" * 300
    files = [("SOUL.md", "s" * 300)]
    out = rehydrate_after_compaction(history, files, budget_chars=100)
    assert len(out) <= 100


def test_rehydrate_after_compaction_drops_injected_blocks() -> None:
    history = render_injected("SOUL.md", "stale injected soul") + "\nreal history"
    files = [("SOUL.md", "fresh soul")]
    out = rehydrate_after_compaction(history, files, budget_chars=2000)
    assert "stale injected soul" not in out
    assert "fresh soul" in out


def test_refresh_standing_backstory_uses_infrastructure_standing() -> None:
    """The loader must not reach upward into cognition for standing assembly."""
    loader = importlib.import_module("lca.infrastructure.memory.contextfiles.service.assembly")
    source = importlib.util.find_spec(
        "lca.infrastructure.memory.contextfiles.service.assembly"
    ).origin
    text = __import__("pathlib").Path(source).read_text(encoding="utf-8")
    assert "lca.cognition" not in text
    assert callable(loader.refresh_standing_backstory)
