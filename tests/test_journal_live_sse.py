"""GET /journal/live behaviour when the process journal is not bound.

The Session Spine lazy-binds the process-wide journal projection on the
first run. Before that, ``/journal/live`` has nothing to stream; the
endpoint must respond with a structured 503 (``legacy_process_journal_unavailable``)
so ``lca-ops logs`` can pick the matching hint instead of falling back to
a generic 500.
"""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from gateway.runs.api import stream_journal_live as api_stream_journal_live
from gateway.runs.query_endpoints import (
    stream_journal_live as query_stream_journal_live,
)


def _client() -> TestClient:
    """Spin up a Starlette app with no journal binding at all."""

    app = Starlette(
        routes=[
            Route("/api/journal/live", api_stream_journal_live, methods=["GET"]),
            Route(
                "/query/journal/live",
                query_stream_journal_live,
                methods=["GET"],
            ),
        ]
    )

    class _Registry:
        class journal:
            @property
            def tail(self):  # pragma: no cover - exercised by both endpoints
                raise RuntimeError(
                    "process journal is not bound; create a run through a journal factory"
                )

    class _State:
        registry = _Registry()

    app.state = _State()  # type: ignore[assignment]
    return TestClient(app, raise_server_exceptions=False)


def _assert_unavailable(payload: dict[str, object], *, where: str) -> None:
    err = payload["error"]
    assert isinstance(err, dict), f"{where}: error envelope should be a dict"
    assert err["code"] == "legacy_process_journal_unavailable", (
        f"{where}: code mismatch ({err['code']!r})"
    )
    assert err["type"] == "service_unavailable", f"{where}: type mismatch ({err['type']!r})"
    assert "process-wide journal streaming is unavailable" in err["message"], where


def test_api_stream_journal_live_unbound_returns_503() -> None:
    client = _client()
    response = client.get("/api/journal/live")
    assert response.status_code == 503, response.text
    _assert_unavailable(response.json(), where="gateway.runs.api")


def test_query_stream_journal_live_unbound_returns_503() -> None:
    client = _client()
    response = client.get("/query/journal/live")
    assert response.status_code == 503, response.text
    _assert_unavailable(response.json(), where="gateway.runs.query_endpoints")


def test_options_request_is_a_noop() -> None:
    client = _client()
    for path in ("/api/journal/live", "/query/journal/live"):
        response = client.options(path)
        assert response.status_code == 200, f"{path}: {response.status_code}"
        assert response.json() == {}, f"{path}: {response.json()}"
