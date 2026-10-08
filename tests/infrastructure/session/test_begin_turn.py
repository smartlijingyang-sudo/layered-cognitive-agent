"""RA-029: begin_turn returns the emitted turn number (or None when unbound)."""

from __future__ import annotations

from unittest.mock import patch

import lca.infrastructure.session.emit.lifecycle_emit as emit_mod


def test_begin_turn_returns_emitted_turn_number() -> None:
    """The emitted turn is returned so the runtime loop can reflect it onto
    the typed AgentState.current_turn seam."""
    appended: list[object] = []
    with (
        patch.object(emit_mod, "_session", return_value=object()),
        patch.object(
            emit_mod, "append_catalog_bound", side_effect=lambda *a, **k: appended.append(a)
        ),
    ):
        assert emit_mod.begin_turn() == 1
        assert emit_mod.begin_turn(turn=3) == 3
    assert len(appended) == 2


def test_begin_turn_returns_none_when_session_unbound() -> None:
    """No session -> nothing emitted -> None (the runtime loop maps this to
    the explicit 0 single-shot default)."""
    with (
        patch.object(emit_mod, "_session", return_value=None),
        patch.object(emit_mod, "append_catalog_bound") as append_mock,
    ):
        assert emit_mod.begin_turn() is None
    append_mock.assert_not_called()
