"""Tests for post-naming scripted flow (Muse-aligned onboarding mechanism).

Covers:
- get_post_naming_messages: bubble count, name variable filling, fixed copy
  contains no variables other than name.
- POST /v1/onboarding/naming/settle: response JSON contains
  followup_messages and show_connectors.
"""

from lca.application.onboarding import get_post_naming_messages
from lca.application.onboarding.script import (
    _POST_NAMING_CONNECT_EN,
    _POST_NAMING_CONNECT_ZH,
    _POST_NAMING_INTRO_EN,
    _POST_NAMING_INTRO_ZH,
)


def test_post_naming_zh_three_bubbles_name_filled():
    msgs = get_post_naming_messages(assistant_name="星澜", locale="zh-CN")
    assert len(msgs) == 3
    # 气泡1：庆祝，name 是变量
    assert msgs[0] == "星澜，名字不错，我喜欢！"
    # 气泡2/3：固定文案
    assert msgs[1] == _POST_NAMING_INTRO_ZH
    assert msgs[2] == _POST_NAMING_CONNECT_ZH


def test_post_naming_en_three_bubbles_name_filled():
    msgs = get_post_naming_messages(assistant_name="zander", locale="en")
    assert len(msgs) == 3
    assert msgs[0] == "zander it is. I like it."
    assert msgs[1] == _POST_NAMING_INTRO_EN
    assert msgs[2] == _POST_NAMING_CONNECT_EN


def test_post_naming_fixed_copy_has_no_other_variables():
    # 固定文案除 name 外不含任何变量占位符
    for const in (
        _POST_NAMING_INTRO_ZH,
        _POST_NAMING_CONNECT_ZH,
        _POST_NAMING_INTRO_EN,
        _POST_NAMING_CONNECT_EN,
    ):
        assert "{" not in const and "}" not in const


def test_post_naming_empty_name_falls_back():
    msgs_zh = get_post_naming_messages(assistant_name="  ", locale="zh")
    assert msgs_zh[0] == "小助，名字不错，我喜欢！"
    msgs_en = get_post_naming_messages(assistant_name="", locale="en")
    assert msgs_en[0] == "Assistant it is. I like it."


def test_post_naming_default_locale_is_zh():
    msgs = get_post_naming_messages(assistant_name="小助")
    assert msgs[0] == "小助，名字不错，我喜欢！"


# ── settle 响应结构 ────────────────────────────────────────────────

import pytest


class _FakeOwnership:
    def __init__(self):
        self.states = {}

    def set_onboarding_state(self, user_id, state):
        self.states[user_id] = state


@pytest.mark.asyncio
async def test_naming_settle_response_carries_followup_and_connectors():
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
    fake_store.states["user_postnaming"] = "pending"
    app.state.assistant_ownership = fake_store

    client = TestClient(app)
    resp = client.post(
        "/v1/onboarding/naming/settle",
        json={"assistant_id": "asst_demo", "name": "星澜", "vibe": "敏锐专注"},
        headers={"x-lca-user-id": "user_postnaming", "Authorization": "Bearer <redacted>"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # 既有字段保持
    assert data["ok"] is True
    assert data["name"] == "星澜"
    assert data["reaction"] == "🎉"

    # 新增：介绍气泡 + 连接器卡片开关
    assert "followup_messages" in data
    assert isinstance(data["followup_messages"], list)
    assert len(data["followup_messages"]) == 3
    assert data["followup_messages"][0] == "星澜，名字不错，我喜欢！"
    assert data["show_connectors"] is True
