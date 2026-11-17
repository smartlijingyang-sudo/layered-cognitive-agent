"""Tests for Mangli enterprise playground offline self-contained web console (INV-06)."""

from starlette.applications import Starlette
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.routes_mangli_playground import (
    PLAYGROUND_ROUTE_SPECS,
)


def test_playground_offline_render():
    app = Starlette()
    for spec in PLAYGROUND_ROUTE_SPECS:
        app.add_route(spec.path, spec.handler, methods=list(spec.methods))

    client = TestClient(app)
    res = client.get("/playground")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "cdn.tailwindcss.com" not in res.text
    assert "unpkg.com" not in res.text
    assert "<style>" in res.text
    # 验证界面包含 WebSocket 首帧认证逻辑
    assert 'type: "auth"' in res.text or '"type": "auth"' in res.text
