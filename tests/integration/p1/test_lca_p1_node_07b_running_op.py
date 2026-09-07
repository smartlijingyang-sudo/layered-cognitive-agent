"""L2-7 (running-op): the HTTP route exists and the null branch works.

The Postgres-running-op store is the PR-3 follow-up (deferred note
``docs/notes/proposed/contract/2026-09-07-p1-facade-ws-token-todo.md``);
the populated-row branch is structurally coupled to a migration that
the LCA dev Postgres fixture does not yet have. The null branch is
already exercised end-to-end via the wire handler in
``lca/.../wire/http.py::get_running_operation``.
"""

from __future__ import annotations

import uuid

from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    build_http_app,
)


def test_running_op_returns_null_for_missing_topic() -> None:
    """A topic_id with no row returns ``{running_operation: null}``."""
    with TestClient(build_http_app()) as client:
        resp = client.get(f"/v1/topics/{uuid.uuid4().hex}/running-op")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"running_operation": None}


def test_running_op_path_is_in_routes_catalog() -> None:
    """The route is wired into the SPEC catalog."""
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.routes import (
        ROUTE_SPECS,
    )

    paths = [spec.path for spec in ROUTE_SPECS]
    assert "/v1/topics/{topic_id}/running-op" in paths