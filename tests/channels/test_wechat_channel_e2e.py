"""End-to-end integration tests for WeChat Channel in LCA."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, call

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.contracts.channels.wechat import WechatQrResult, WechatStatusResult
from lca.infrastructure.channels.wechat.formatter import WechatMessageFormatter
from lca.infrastructure.channels.wechat.manager import WechatChannelManager
from lca.infrastructure.channels.wechat.worker import derive_wechat_session_id
from lca.plugins.transport.webserver.routes_channels_wechat import (
    wechat_bind,
    wechat_config,
    wechat_qrcode,
    wechat_status,
    wechat_unbind,
)


def _create_gateway_app(client_mock: AsyncMock, manager: WechatChannelManager) -> Starlette:
    routes = [
        Route("/lca-api/channels/wechat/qrcode", wechat_qrcode, methods=["GET", "OPTIONS"]),
        Route("/lca-api/channels/wechat/status", wechat_status, methods=["GET", "OPTIONS"]),
        Route("/lca-api/channels/wechat/bind", wechat_bind, methods=["POST", "OPTIONS"]),
        Route("/lca-api/channels/wechat/unbind", wechat_unbind, methods=["POST", "OPTIONS"]),
        Route("/lca-api/channels/wechat/config", wechat_config, methods=["GET", "OPTIONS"]),
        Route("/channels/wechat/qrcode", wechat_qrcode, methods=["GET", "OPTIONS"]),
        Route("/channels/wechat/status", wechat_status, methods=["GET", "OPTIONS"]),
        Route("/channels/wechat/bind", wechat_bind, methods=["POST", "OPTIONS"]),
        Route("/channels/wechat/unbind", wechat_unbind, methods=["POST", "OPTIONS"]),
        Route("/channels/wechat/config", wechat_config, methods=["GET", "OPTIONS"]),
    ]
    app = Starlette(routes=routes)
    app.state.wechat_client = client_mock
    app.state.wechat_manager = manager
    return app


@pytest.mark.asyncio
async def test_full_wechat_channel_lifecycle_and_messaging_flow(tmp_path):
    """Verify full loop: QR code -> Status -> Bind -> Inbound message -> Typing & Progress -> Reply -> Unbind."""
    client_mock = AsyncMock()

    dispatched_events: list[tuple[str, str, str]] = []

    async def simulated_cognitive_dispatch(
        assistant_id: str,
        session_id: str,
        user_prompt: str,
        progress_callback=None,
    ) -> str:
        dispatched_events.append((assistant_id, session_id, user_prompt))
        if progress_callback:
            # 1) Send thought progress
            thought_text = WechatMessageFormatter.format_step_progress(
                step_type="thinking",
                thinking_text="正在检查主机运行状态与核心指标...",
            )
            await progress_callback(thought_text)
            # 2) Send tool calling progress
            tool_call_text = WechatMessageFormatter.format_step_progress(
                step_type="tools_calling",
                tools_calling=[{"identifier": "system", "api_name": "get_system_metrics", "summary_arg": "cpu"}],
                total_tool_calls=1,
            )
            await progress_callback(tool_call_text)
            # 3) Send tool result progress
            tool_done_text = WechatMessageFormatter.format_step_progress(
                step_type="tools_result",
                tools_calling=[{"identifier": "system", "api_name": "get_system_metrics", "summary_arg": "cpu"}],
                tools_result=[{"is_success": True, "output": "CPU load: 15.2%"}],
                total_tool_calls=1,
                elapsed_seconds=0.25,
            )
            await progress_callback(tool_done_text)

        # 4) Final reply
        return WechatMessageFormatter.format_final_reply(
            "当前系统运行正常，CPU 负载为 15.2%，处于健康区间。"
        )

    manager = WechatChannelManager(
        base_dir=tmp_path,
        dispatch_fn=simulated_cognitive_dispatch,
        client_factory=lambda _: client_mock,
    )
    app = _create_gateway_app(client_mock, manager)
    http_client = TestClient(app)

    # 1. Step 1: Client fetches QR code
    client_mock.fetch_qrcode.return_value = WechatQrResult(
        qrcode="qrc_test_token_123",
        qrcode_img_content="https://weixin.qq.com/x/test_qr_url",
    )
    qr_resp = http_client.get("/lca-api/channels/wechat/qrcode")
    assert qr_resp.status_code == 200
    assert qr_resp.json()["qrcode"] == "qrc_test_token_123"

    # 2. Step 2: Client polls QR status (simulate wait then confirmed)
    client_mock.poll_qrcode_status.side_effect = [
        WechatStatusResult(status="wait"),
        WechatStatusResult(
            status="confirmed",
            bot_token="tok_secret_wechat_888",  # noqa: S106
            ilink_bot_id="bot_wechat_001@im.bot",
            ilink_user_id="wx_user_super_admin@im.wechat",
        ),
    ]

    status_1 = http_client.get("/lca-api/channels/wechat/status?qrcode=qrc_test_token_123")
    assert status_1.status_code == 200
    assert status_1.json()["status"] == "wait"

    status_2 = http_client.get("/lca-api/channels/wechat/status?qrcode=qrc_test_token_123")
    assert status_2.status_code == 200
    status_data = status_2.json()
    assert status_data["status"] == "confirmed"
    assert status_data["bot_token"] == "tok_secret_wechat_888"  # noqa: S105
    assert status_data["ilink_bot_id"] == "bot_wechat_001@im.bot"

    # Configure mock responses for message long-polling before binding
    user_wechat_id = "wx_user_john_doe@im.wechat"
    inbound_message = {
        "ret": 0,
        "get_updates_buf": "buf_step_01",
        "msgs": [
            {
                "from_user_id": user_wechat_id,
                "context_token": "ctx_token_alpha_beta",
                "item_list": [{"type": 1, "text_item": {"text": "请分析当前系统负载并报告。"}}],
            }
        ],
    }

    async def mock_get_updates_handler(*args, **kwargs):
        if not hasattr(mock_get_updates_handler, "_called"):
            mock_get_updates_handler._called = True
            return inbound_message
        await asyncio.sleep(0.1)
        return {"ret": 0, "msgs": []}

    client_mock.get_updates.side_effect = mock_get_updates_handler
    client_mock.send_typing.return_value = True
    client_mock.send_message.return_value = True

    # 3. Step 3: Assistant binds the channel
    asst_id = "asst_arch_e2e_001"
    bind_resp = http_client.post(
        "/lca-api/channels/wechat/bind",
        json={
            "assistant_id": asst_id,
            "bot_token": status_data["bot_token"],
            "ilink_bot_id": status_data["ilink_bot_id"],
            "ilink_user_id": status_data["ilink_user_id"],
            "display_tool_calls": True,
        },
    )
    assert bind_resp.status_code == 200
    assert bind_resp.json()["ok"] is True
    assert manager.is_running(asst_id)

    # Verify config endpoint reflection
    cfg_resp = http_client.get(f"/channels/wechat/config?assistant_id={asst_id}")
    assert cfg_resp.status_code == 200
    cfg_data = cfg_resp.json()
    assert cfg_data["is_running"] is True
    assert cfg_data["config"]["bot_id"] == "bot_wechat_001@im.bot"

    # 4. Step 4: Wait for worker background poll loop to process inbound message
    for _ in range(30):
        if len(dispatched_events) > 0:
            break
        await asyncio.sleep(0.05)

    # Verify session derivation and dispatch
    assert len(dispatched_events) == 1
    d_asst, d_sess, d_prompt = dispatched_events[0]
    expected_sess = derive_wechat_session_id(asst_id, user_wechat_id)
    assert d_asst == asst_id
    assert d_sess == expected_sess
    assert d_prompt == "请分析当前系统负载并报告。"

    # Verify typing lifecycle
    client_mock.send_typing.assert_has_calls([
        call(status_data["bot_token"], user_wechat_id, "", start=True),
        call(status_data["bot_token"], user_wechat_id, "", start=False),
    ])

    # Verify progress notifications sent to user
    sent_calls = client_mock.send_message.call_args_list
    assert len(sent_calls) >= 4  # 3 progress + 1 final reply

    # Verify thoughts in progress
    assert any("正在检查主机运行状态" in str(c) for c in sent_calls)
    # Verify tool call in progress
    assert any("get_system_metrics" in str(c) for c in sent_calls)
    # Verify final formatted output with replyTemplate formatting
    assert any("当前系统运行正常，CPU 负载为 15.2%" in str(c) for c in sent_calls)
    assert any("ctx_token_alpha_beta" in str(c) for c in sent_calls)

    # 5. Step 5: Unbind channel
    unbind_resp = http_client.post(
        "/channels/wechat/unbind",
        json={"assistant_id": asst_id},
    )
    assert unbind_resp.status_code == 200
    assert not manager.is_running(asst_id)

    # Verify config is cleared
    cfg_after = http_client.get(f"/lca-api/channels/wechat/config?assistant_id={asst_id}")
    assert cfg_after.json()["is_running"] is False
    assert cfg_after.json()["config"] is None

    await manager.shutdown()


@pytest.mark.asyncio
async def test_wechat_channel_edge_cases_and_error_handling(tmp_path):
    """Verify error responses: missing parameters, expired QR code, and unbinding non-existent channels."""
    client_mock = AsyncMock()
    manager = WechatChannelManager(base_dir=tmp_path, client_factory=lambda _: client_mock)
    app = _create_gateway_app(client_mock, manager)
    http_client = TestClient(app)

    # 1. Status query missing qrcode query param -> 400
    resp = http_client.get("/lca-api/channels/wechat/status")
    assert resp.status_code == 400
    assert "qrcode" in resp.json()["error"]

    # 2. Config query missing assistant_id query param -> 400
    resp = http_client.get("/lca-api/channels/wechat/config")
    assert resp.status_code == 400
    assert "assistant_id" in resp.json()["error"]

    # 3. Bind missing credentials -> 400
    resp = http_client.post("/lca-api/channels/wechat/bind", json={"assistant_id": "asst_x"})
    assert resp.status_code == 400
    assert "Missing required credentials" in resp.json()["error"]

    # 4. Unbind missing assistant_id -> 400
    resp = http_client.post("/lca-api/channels/wechat/unbind", json={})
    assert resp.status_code == 400

    # 5. Unbind non-existent assistant -> 200 (idempotent)
    resp = http_client.post("/lca-api/channels/wechat/unbind", json={"assistant_id": "non_existent"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 6. Expired QR status returned from iLink
    client_mock.poll_qrcode_status.return_value = WechatStatusResult(status="expired")
    resp = http_client.get("/channels/wechat/status?qrcode=qrc_expired_999")
    assert resp.status_code == 200
    assert resp.json()["status"] == "expired"

    await manager.shutdown()

