"""RA-134: direct unit tests for the lobehub fallback seam's fail-soft paths.

``agent_assistant_id_from_lobehub`` (lca/infrastructure/persistence/lobehub_agents.py)
is the cheapest seam in the repo to test (46-line pure function), yet the
existing tests (4f67f10d7) all monkeypatch it away: they prove the carrier
calls the seam correctly, but nobody proves the seam itself is correct.
``except Exception: return None`` without tests is not a contract.

These five tests pin the None contract for the five fail-soft paths, using
a fake ``postgres_connection`` contextmanager stub -- no real DB. They
deliberately do NOT pin the SQL text: the ``agency_config`` column is
ADR-0187 D7 domain knowledge and its change is ADR-driven.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import pytest

from lca.infrastructure.persistence import lobehub_agents
from lca.infrastructure.persistence.lobehub_agents import (
    agent_assistant_id_from_lobehub,
)


class _FakeCursor:
    """Minimal cursor stub: records nothing, replays one canned row."""

    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def execute(self, _sql: str, _params: tuple[object, ...]) -> None:
        pass

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _FakeConnection:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._row)


@contextlib.contextmanager
def _connection_stub(
    url: str, row: tuple[Any, ...] | None = None
) -> Iterator[_FakeConnection]:
    yield _FakeConnection(row)


@contextlib.contextmanager
def _refusing_connection(url: str) -> Iterator[_FakeConnection]:
    raise RuntimeError("connection refused")
    yield  # pragma: no cover - unreachable


@pytest.fixture()
def _db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend a Postgres URL is configured (never touched for real)."""
    monkeypatch.setattr(lobehub_agents, "lobehub_database_url", lambda: "postgresql://fake")


def test_empty_agent_id_returns_none(_db_url: None) -> None:
    assert agent_assistant_id_from_lobehub("") is None


def test_no_database_url_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lobehub_agents, "lobehub_database_url", lambda: "")
    assert agent_assistant_id_from_lobehub("agt_123") is None


def test_connection_failure_returns_none(
    _db_url: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lobehub_agents, "postgres_connection", _refusing_connection)
    assert agent_assistant_id_from_lobehub("agt_123") is None


def test_missing_row_returns_none(
    _db_url: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        lobehub_agents, "postgres_connection", lambda url: _connection_stub(url, None)
    )
    assert agent_assistant_id_from_lobehub("agt_123") is None


def test_row_without_mapping_returns_none(
    _db_url: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # agency_config lacks the lcaAssistantId key -> the SELECT yields NULL.
    monkeypatch.setattr(
        lobehub_agents,
        "postgres_connection",
        lambda url: _connection_stub(url, (None,)),
    )
    assert agent_assistant_id_from_lobehub("agt_123") is None
