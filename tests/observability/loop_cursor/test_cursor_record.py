"""Tests for ``CursorRecord``, the process-wide cursor DI holder.

``CursorRecord`` moved from ``lca.cognition.body.executor`` into
``lca.infrastructure.observability.loop_cursor`` so infrastructure adapters,
plugins, and cognition nodes all depend on it without an upward import.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lca.contracts.observability.cursor.loop_cursor import CursorError, LoopCursor, PhaseName
from lca.infrastructure.observability.loop_cursor.cursor_record import CursorRecord

if TYPE_CHECKING:
    import pytest

REPO = Path(__file__).resolve().parents[3]


class _FakeCursor(LoopCursor):
    """Minimal LoopCursor recording advance calls."""

    def __init__(self) -> None:
        self.advances: list[tuple[PhaseName, dict[str, object]]] = []
        self._phase: PhaseName = "init"

    @property
    def snapshot(self) -> object:
        return type("Snap", (), {"phase": self._phase})()

    def advance(self, target: PhaseName, **kwargs: object) -> None:
        self._phase = target
        self.advances.append((target, kwargs))


def test_bind_and_get_roundtrip() -> None:
    cursor = _FakeCursor()
    previous = CursorRecord.bind(cursor)
    assert previous is None
    assert CursorRecord.get() is cursor
    CursorRecord.bind(None)


def test_bind_returns_previous() -> None:
    first = _FakeCursor()
    second = _FakeCursor()
    CursorRecord.bind(first)
    assert CursorRecord.bind(second) is first
    CursorRecord.bind(None)


def test_get_returns_none_when_unbound() -> None:
    CursorRecord.bind(None)
    assert CursorRecord.get() is None


def test_try_advance_noop_when_unbound() -> None:
    CursorRecord.bind(None)
    # Should not raise.
    CursorRecord.try_advance("think")


def test_try_advance_forwards_to_cursor() -> None:
    cursor = _FakeCursor()
    CursorRecord.bind(cursor)
    CursorRecord.try_advance("think", action_type="model_name")
    assert cursor.advances == [("think", {})]
    assert cursor._phase == "think"
    CursorRecord.bind(None)


def test_try_advance_swallows_cursor_error(capsys: pytest.CaptureFixture[str]) -> None:
    class _BrokenCursor(_FakeCursor):
        def advance(self, target: PhaseName, **kwargs: object) -> None:
            raise CursorError("boom")

    CursorRecord.bind(_BrokenCursor())
    CursorRecord.try_advance("think")
    captured = capsys.readouterr()
    assert "error=boom" in captured.out or "error=boom" in captured.err
    CursorRecord.bind(None)


def test_cursor_record_no_longer_in_cognition() -> None:
    old = REPO / "lca" / "cognition" / "body" / "executor" / "cursor_record.py"
    assert not old.exists()
    new = REPO / "lca" / "infrastructure" / "observability" / "loop_cursor" / "cursor_record.py"
    assert new.exists()


def test_observability_adapters_no_cognition_import() -> None:
    source = (
        REPO / "lca" / "infrastructure" / "observability" / "adapters" / "adapters.py"
    ).read_text(encoding="utf-8")
    assert "lca.cognition" not in source
