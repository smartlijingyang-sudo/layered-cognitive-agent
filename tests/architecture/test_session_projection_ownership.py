"""The session registry delegates carrier payload projection to its own module."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_session_projection_owns_summary_payload_shape() -> None:
    projection = _source(ROOT / "gateway" / "runs" / "session_projection.py")
    registry = _source(ROOT / "gateway" / "runs" / "session.py")

    assert "def summary_for_session" in projection
    assert '"approval_request"' in projection
    assert "summary_for_session(session)" in registry
    assert '"session_status"' not in registry


def test_session_projection_keeps_registry_import_type_only() -> None:
    projection = _source(ROOT / "gateway" / "runs" / "session_projection.py")

    assert "if TYPE_CHECKING:" in projection
    assert "from gateway.runs.session.session import RunSession" in projection
