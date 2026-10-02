# -*- coding: utf-8 -*-
"""Onboarding 主动欢迎消息回归测试。

复现用户报告的 bug：onboarding naming_settle 完成后，期望中的主动欢迎消息
前端拿不到——旧代码的 settle 响应只有 {"ok","reaction"}，没有任何消息字段。

锁定修复：settle 响应必须携带 welcome_message（RESPONSE_CARRIED），
前端在已有请求-响应链路上直接渲染为 assistant 气泡。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


class _FakeOwnership:
    def __init__(self) -> None:
        self.states: dict[str, str] = {}
        self.user_mds: dict[str, str] = {}

    def get_onboarding_state(self, user_id: str) -> str:
        return self.states.get(user_id, "pending")

    def set_onboarding_state(self, user_id: str, state: str) -> None:
        self.states[user_id] = state

    def get_user_md(self, user_id: str) -> str | None:
        return self.user_mds.get(user_id)


def _client():
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from lca.plugins.transport.webserver.router.router import RouteRegistry
    from lca.plugins.transport.webserver.routes_1.routes_onboarding import (
        onboarding_naming_settle,
    )

    app = Starlette()
    router = RouteRegistry()
    router.register_http(
        Route("/v1/onboarding/naming/settle", onboarding_naming_settle, methods=["POST", "OPTIONS"])
    )
    router.install(app)
    fake_store = _FakeOwnership()
    fake_store.states["user_welcome"] = "pending"
    app.state.assistant_ownership = fake_store
    return TestClient(app), fake_store


def test_settle_response_carries_welcome_message():
    client, fake_store = _client()
    resp = client.post(
        "/v1/onboarding/naming/settle",
        json={"assistant_id": "asst_demo", "name": "星澜", "vibe": "敏锐专注"},
        headers={"x-lca-user-id": "user_welcome", "Authorization": "Bearer <redacted>"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # 主流程不受影响
    assert data["ok"] is True
    assert data["name"] == "星澜"
    assert fake_store.states["user_welcome"] == "completed"
    # 回归断言：欢迎消息必须在响应里（旧代码缺失此字段）
    assert "welcome_message" in data, "settle 响应缺 welcome_message（bug 复现）"
    assert data["welcome_message"], "welcome_message 不得为空"
    assert "星澜" in data["welcome_message"]


def test_settle_welcome_message_zh_default():
    client, _ = _client()
    resp = client.post(
        "/v1/onboarding/naming/settle",
        json={"assistant_id": "asst_demo", "name": "小助", "vibe": ""},
        headers={"x-lca-user-id": "user_welcome", "Authorization": "Bearer <redacted>"},
    )
    assert resp.status_code == 200
    msg = resp.json()["welcome_message"]
    assert msg is not None
    # 默认中文文案
    assert "你好" in msg or "朋友" in msg


def test_settle_still_ok_when_welcome_pipeline_fails(monkeypatch):
    """欢迎消息管线抛错时 settle 主流程不受影响（fail-soft）。"""
    import lca.application.onboarding.script as script_mod

    def _boom(**kwargs):
        raise RuntimeError("simulated greeting failure")

    monkeypatch.setattr(script_mod, "get_onboarding_opening_messages", _boom)
    client, fake_store = _client()
    resp = client.post(
        "/v1/onboarding/naming/settle",
        json={"assistant_id": "asst_demo", "name": "星澜", "vibe": "敏锐专注"},
        headers={"x-lca-user-id": "user_welcome", "Authorization": "Bearer <redacted>"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert fake_store.states["user_welcome"] == "completed"
    assert data["welcome_message"] is None
