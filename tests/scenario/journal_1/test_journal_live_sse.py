"""``GET /journal/live`` behavior across boot-time capability gating.

ADR-0163 决策 3:``/journal/live`` is registered **only when** the
``process_journal`` capability is bound on the boot ``ctx``. Reaching
the handler therefore implies the owner can stream frames; ``None``
from ``stream_process_journal_live`` is a port bug, not a 503 envelope.
"""

from __future__ import annotations

from typing import Any

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.runs.api.query_endpoints import (
    stream_journal_live as query_stream_journal_live,
)


class _OwningRunPort:
    """Owner that hands back a streaming generator for the process journal."""

    def stream_process_journal_live(self, last_seq: int = 0) -> Any:
        async def _gen():
            yield b"data: ok\n\n"

        return _gen()


def _client_with_owner() -> TestClient:
    app = Starlette(
        routes=[Route("/query/journal/live", query_stream_journal_live, methods=["GET", "OPTIONS"])]
    )
    app.state.run_port = _OwningRunPort()  # type: ignore[attr-defined]
    return TestClient(app, raise_server_exceptions=False)


def test_options_request_is_a_noop() -> None:
    response = _client_with_owner().options("/query/journal/live")
    assert response.status_code == 200, response.text
    assert response.json() == {}, response.json()


def test_stream_journal_live_emits_frames_when_owner_supports_it() -> None:
    response = _client_with_owner().get("/query/journal/live")
    assert response.status_code == 200, response.text
    assert b"data: ok" in response.content
