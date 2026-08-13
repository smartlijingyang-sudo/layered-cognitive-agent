"""File URLs stay relative. gateway must not absolutize."""

from __future__ import annotations

from pathlib import Path


def test_gateway_has_no_absolutize_helpers() -> None:
    for path in Path("gateway").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "absolutize_" not in text
        assert "def gateway_public_base" not in text
