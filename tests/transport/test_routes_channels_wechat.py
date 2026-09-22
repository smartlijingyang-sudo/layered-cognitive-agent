"""Tests for routes_channels_wechat Starlette routes."""

from unittest.mock import AsyncMock

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.contracts.channels.wechat import WechatChannelConfig, WechatQrResult, WechatStatusResult
from lca.plugins.transport.webserver.routes_channels_wechat import (
    wechat_bind,
    wechat_config,
    wechat_qrcode,
    wechat_status,
    wechat_unbind,
)


def create_test_app(mock_client=None, mock_manager=None):
    app = Starlette(
        routes=[
            Route("/lca-api/channels/wechat/qrcode", wechat_qrcode, methods=["GET", "OPTIONS"]),
            Route("/lca-api/channels/wechat/status", wechat_status, methods=["GET", "OPTIONS"]),
            Route("/lca-api/channels/wechat/bind", wechat_bind, methods=["POST", "OPTIONS"]),
            Route("/lca-api/channels/wechat/unbind", wechat_unbind, methods=["POST", "OPTIONS"]),
            Route("/lca-api/channels/wechat/config", wechat_config, methods=["GET", "OPTIONS"]),
        ]
    )
    app.state.wechat_client = mock_client
    app.state.wechat_manager = mock_manager
    return app


def test_wechat_qrcode_endpoint():
    mock_client = AsyncMock()
    mock_client.fetch_qrcode.return_value = WechatQrResult(
        qrcode="qrc_xyz",
        qrcode_img_content="https://weixin.qq.com/x/xyz",
    )

    app = create_test_app(mock_client=mock_client)
    client = TestClient(app)

    resp = client.get("/lca-api/channels/wechat/qrcode")
    assert resp.status_code == 200
    data = resp.json()
    assert data["qrcode"] == "qrc_xyz"
    assert data["qrcode_img_content"] == "https://weixin.qq.com/x/xyz"


def test_wechat_status_endpoint():
    mock_client = AsyncMock()
    mock_client.poll_qrcode_status.return_value = WechatStatusResult(
        status="confirmed",
        bot_token="token_val",  # noqa: S106
        ilink_bot_id="bot@im.bot",
        ilink_user_id="user@im.wechat",
    )

    app = create_test_app(mock_client=mock_client)
    client = TestClient(app)

    resp = client.get("/lca-api/channels/wechat/status?qrcode=qrc_xyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "confirmed"
    assert data["bot_token"] == "token_val"  # noqa: S105
    assert data["ilink_bot_id"] == "bot@im.bot"
    assert data["ilink_user_id"] == "user@im.wechat"


def test_wechat_bind_endpoint():
    mock_manager = AsyncMock()
    mock_manager.bind_channel.return_value = None

    app = create_test_app(mock_manager=mock_manager)
    client = TestClient(app)

    payload = {
        "assistant_id": "asst_001",
        "bot_id": "bot@im.bot",
        "bot_token": "token_val",
        "user_id": "user@im.wechat",
        "enabled": True,
        "display_tool_calls": True,
    }
    resp = client.post("/lca-api/channels/wechat/bind", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "assistant_id": "asst_001"}
    mock_manager.bind_channel.assert_called_once()


def test_wechat_unbind_endpoint():
    mock_manager = AsyncMock()
    mock_manager.unbind_channel.return_value = None

    app = create_test_app(mock_manager=mock_manager)
    client = TestClient(app)

    resp = client.post("/lca-api/channels/wechat/unbind", json={"assistant_id": "asst_001"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "assistant_id": "asst_001"}
    mock_manager.unbind_channel.assert_called_once_with("asst_001")


def test_wechat_config_endpoint():
    from unittest.mock import MagicMock
    mock_manager = AsyncMock()
    mock_manager.get_channel_config = MagicMock(return_value=WechatChannelConfig(
        bot_id="bot@im.bot",
        bot_token="token_val",  # noqa: S106
        user_id="user@im.wechat",
        display_tool_calls=True,
    ))
    mock_manager.is_running = MagicMock(return_value=True)

    app = create_test_app(mock_manager=mock_manager)
    client = TestClient(app)

    resp = client.get("/lca-api/channels/wechat/config?assistant_id=asst_001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_running"] is True
    assert data["config"]["bot_id"] == "bot@im.bot"
