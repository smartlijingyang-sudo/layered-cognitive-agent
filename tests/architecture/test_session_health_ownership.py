"""The registry delegates carrier health projection to its own module."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_session_health_owns_combined_health_projection() -> None:
    health = _source(ROOT / "gateway" / "runs" / "session_health.py")
    registry = _source(ROOT / "gateway" / "runs" / "session.py")

    assert "class RunHealthProjection" in health
    assert 'totals["journal_subscribers"]' in health
    assert "return self._health.status_counts()" in registry
    assert "return self._health.live_totals()" in registry


def test_registry_does_not_assemble_health_payload() -> None:
    registry = _source(ROOT / "gateway" / "runs" / "session.py")

    assert "self._index.status_counts()" not in registry
    assert "self._index.live_tail_totals()" not in registry
    assert "self._process_journal.subscriber_count" not in registry
