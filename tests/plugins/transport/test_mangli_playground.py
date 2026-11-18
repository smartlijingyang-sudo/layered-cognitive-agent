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


def test_playground_encrypt_api():
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import decrypt_mangli_user_header

    app = Starlette()
    for spec in PLAYGROUND_ROUTE_SPECS:
        app.add_route(spec.path, spec.handler, methods=list(spec.methods))

    client = TestClient(app)
    res = client.post(
        "/playground/encrypt",
        json={
            "payload": {
                "userId": "10001",
                "name": "张三",
                "jobNumber": "E10001",
                "mobile": "13800138000",
                "email": "zhangsan@company.com",
                "jobName": "架构师",
                "department": "技术部",
                "clockInType": 1,
                "ticket": "TKT-MANGLI-001",
            },
            "key": "0123456789abcdef0123456789abcdef",
            "key_mode": "hex",
        },
    )
    assert res.status_code == 200
    cipher_hex = res.json()["cipher_hex"]
    assert cipher_hex

    # 验证生成的密文可被后端解密且字段 100% 对齐
    decrypted = decrypt_mangli_user_header(cipher_hex, bytes.fromhex("0123456789abcdef0123456789abcdef"))
    assert decrypted["userId"] == "10001"
    assert decrypted["name"] == "张三"
    assert decrypted["jobNumber"] == "E10001"
    assert decrypted["ticket"] == "TKT-MANGLI-001"
