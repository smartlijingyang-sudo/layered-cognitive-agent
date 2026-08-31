"""GET /journal/live behaviour when the process journal is not bound.

The Session Spine lazy-binds the process-wide journal projection on the
first run. Before that, ``/journal/live`` has nothing to stream; the
endpoint must respond with a structured 503
(``legacy_process_journal_unavailable``) so ``lca-ops logs`` can pick the
matching hint instead of falling back to a generic 500.

Both ``lca.plugins.transport.webserver.handlers.runs.api.routes.stream_journal_live`` (legacy soft-lock surface)
and ``lca.plugins.transport.webserver.handlers.runs.api.routes.query_endpoints.stream_journal_live`` (the
Session Spine module that owns ``app.state.run_port``) must surface the
same refusal envelope so the wire shape stays stable.
"""

from __future__ import annotations

from typing import Any

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.runs.api.query_endpoints import (
    stream_journal_live as query_stream_journal_live,
)
from lca.plugins.transport.webserver.handlers.runs.api.routes import (
    stream_journal_live as api_stream_journal_live,
)


class _UnboundProcessJournal:
    """Raising stand-in for ``RunRegistry.journal`` before any run binds it."""

    @property
    def tail(self) -> Any:
        raise RuntimeError("process journal is not bound; create a run through a journal factory")


class _UnboundRegistry:
    journal = _UnboundProcessJournal()


class _UnboundRunPort:
    def stream_process_journal_live(self, last_seq: int = 0) -> Any:
        return None  # ``query_endpoints`` treats ``None`` as "not available"


class _State:
    registry = _UnboundRegistry()
    run_port = _UnboundRunPort()


def _client() -> TestClient:
    app = Starlette(
        routes=[
            Route(
                "/api/journal/live",
                api_stream_journal_live,
                methods=["GET", "OPTIONS"],
            ),
            Route(
                "/query/journal/live",
                query_stream_journal_live,
                methods=["GET", "OPTIONS"],
            ),
        ]
    )
    app.state = _State()  # type: ignore[assignment]
    return TestClient(app, raise_server_exceptions=False)


def _assert_unavailable(payload: dict[str, Any], *, where: str) -> None:
    err = payload.get("error")
    assert isinstance(err, dict), f"{where}: error envelope should be a dict, got {payload!r}"
    assert err.get("code") == "legacy_process_journal_unavailable", (
        f"{where}: code mismatch ({err.get('code')!r})"
    )
    assert err.get("type") == "service_unavailable", f"{where}: type mismatch ({err.get('type')!r})"
    assert "process-wide journal streaming is unavailable" in err.get("message", ""), where


def test_api_stream_journal_live_unbound_returns_503() -> None:
    client = _client()
    response = client.get("/api/journal/live")
    assert response.status_code == 503, response.text
    _assert_unavailable(
        response.json(), where="lca.plugins.transport.webserver.handlers.runs.api.routes"
    )


def test_query_stream_journal_live_unbound_returns_503() -> None:
    client = _client()
    response = client.get("/query/journal/live")
    assert response.status_code == 503, response.text
    _assert_unavailable(
        response.json(),
        where="lca.plugins.transport.webserver.handlers.runs.api.routes.query_endpoints",
    )


def test_options_request_is_a_noop() -> None:
    client = _client()
    for path in ("/api/journal/live", "/query/journal/live"):
        response = client.options(path)
        assert response.status_code == 200, f"{path}: {response.status_code} {response.text}"
        assert response.json() == {}, f"{path}: {response.json()}"
