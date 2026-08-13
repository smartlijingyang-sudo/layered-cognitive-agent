"""Presence / Console stay split: registry and book have no Starlette."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path("gateway")


def _source(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_registry_has_no_starlette() -> None:
    assert "starlette" not in _source("presence/registry.py")


def test_sessions_has_no_starlette() -> None:
    assert "starlette" not in _source("console/sessions.py")


def test_wire_has_no_starlette() -> None:
    assert "starlette" not in _source("presence/wire.py")


def test_host_does_not_import_console() -> None:
    text = Path("host/client.py").read_text(encoding="utf-8")
    assert "gateway.console" not in text


def test_api_does_not_import_app() -> None:
    assert "gateway.app" not in _source("presence/api.py")
    assert "gateway.app" not in _source("console/api.py")
