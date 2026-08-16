"""Tests for ``lca.harness.diagnostics.tree.render_tree`` (A.6)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lca.harness.diagnostics.tree import render_tree


def _make_handle(
    entry_id: str,
    *,
    state: str = "ACTIVE",
    provides: tuple[str, ...] = (),
    injected: tuple[str, ...] = (),
    effects: int = 0,
) -> MagicMock:
    h = MagicMock()
    h.entry_id = entry_id
    h.state = state
    h.spec.provides = provides
    h.injected = injected
    h.effects = list(range(effects))
    return h


class TestRenderTree:
    def test_render_empty_host(self) -> None:
        host = MagicMock()
        host.handles = {}
        output = render_tree(host)
        assert "plugin tree" in output.lower()
        assert "empty" in output.lower()

    def test_render_single_plugin(self) -> None:
        handle = _make_handle(
            "lca.llm.service",
            provides=("llm",),
            injected=("memory",),
            effects=2,
        )
        host = MagicMock()
        host.handles = {"lca.llm.service": handle}
        output = render_tree(host)
        assert "lca.llm.service" in output
        assert "ACTIVE" in output
        assert "llm" in output
        assert "memory" in output
        assert "2" in output  # effect count

    def test_render_multiple_plugins_sorted(self) -> None:
        host = MagicMock()
        host.handles = {
            "z.plugin": _make_handle("z.plugin", state="FAILED"),
            "a.plugin": _make_handle("a.plugin", state="ACTIVE", provides=("x", "y")),
        }
        output = render_tree(host)
        # alphabetical order
        assert output.index("a.plugin") < output.index("z.plugin")
        assert "FAILED" in output
        assert "x, y" in output

    def test_hide_effects_flag(self) -> None:
        host = MagicMock()
        host.handles = {"p": _make_handle("p", effects=3)}
        output = render_tree(host, show_effects=False)
        assert "effects" not in output

    def test_total_plugins_summary(self) -> None:
        host = MagicMock()
        host.handles = {
            "a": _make_handle("a"),
            "b": _make_handle("b"),
            "c": _make_handle("c"),
        }
        output = render_tree(host)
        assert "total plugins: 3" in output

    def test_enum_state_unwrapped(self) -> None:
        """state can be an enum with a .value attribute."""
        from enum import Enum

        class PluginState(str, Enum):
            ACTIVE = "active"

        handle = _make_handle("p")
        handle.state = PluginState.ACTIVE
        host = MagicMock()
        host.handles = {"p": handle}
        output = render_tree(host)
        assert "active" in output  # unwrapped from enum


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
