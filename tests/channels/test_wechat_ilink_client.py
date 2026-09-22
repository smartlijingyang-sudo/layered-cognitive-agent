import json

import httpx
import pytest

from lca.infrastructure.channels.wechat.client import WechatIlinkClient


@pytest.mark.asyncio
async def test_fetch_qrcode():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/ilink/bot/get_bot_qrcode" in str(request.url)
        assert request.url.params.get("bot_type") == "3"
        return httpx.Response(
            200,
            json={"qrcode": "qrc_test_123", "qrcode_img_content": "https://weixin.qq.com/x/test"},
        )

    transport = httpx.MockTransport(handler)
    client = WechatIlinkClient(transport=transport)
    result = await client.fetch_qrcode()

    assert result.qrcode == "qrc_test_123"
    assert result.qrcode_img_content == "https://weixin.qq.com/x/test"


@pytest.mark.asyncio
async def test_poll_qrcode_status():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/ilink/bot/get_qrcode_status" in str(request.url)
        assert request.headers.get("iLink-App-ClientVersion") == "1"
        qrcode = request.url.params.get("qrcode")

        if qrcode == "qrc_wait":
            return httpx.Response(200, json={"status": "wait"})
        if qrcode == "qrc_confirmed":
            return httpx.Response(
                200,
                json={
                    "status": "confirmed",
                    "bot_token": "token_abc",
                    "ilink_bot_id": "bot_1@im.bot",
                    "ilink_user_id": "user_1@im.wechat",
                    "baseurl": "https://ilinkai.weixin.qq.com",
                },
            )
        return httpx.Response(200, json={"status": "expired"})

    transport = httpx.MockTransport(handler)
    client = WechatIlinkClient(transport=transport)

    res_wait = await client.poll_qrcode_status("qrc_wait")
    assert res_wait.status == "wait"
    assert res_wait.bot_token is None

    res_conf = await client.poll_qrcode_status("qrc_confirmed")
    assert res_conf.status == "confirmed"
    assert res_conf.bot_token == "token_abc"  # noqa: S105
    assert res_conf.ilink_bot_id == "bot_1@im.bot"
    assert res_conf.ilink_user_id == "user_1@im.wechat"

    res_exp = await client.poll_qrcode_status("qrc_expired")
    assert res_exp.status == "expired"


@pytest.mark.asyncio
async def test_get_updates_headers_and_body():
    requests_received = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_received.append(request)
        assert request.method == "POST"
        assert "/ilink/bot/getupdates" in str(request.url)
        assert request.headers.get("Authorization") == "Bearer my_test_token"
        assert request.headers.get("AuthorizationType") == "ilink_bot_token"
        assert request.headers.get("X-WECHAT-UIN") is not None
        body = json.loads(request.read())
        assert body["base_info"]["channel_version"] == "1.0.0"
        assert body["get_updates_buf"] == "cursor_prev"
        return httpx.Response(
            200,
            json={
                "ret": 0,
                "get_updates_buf": "cursor_next",
                "msgs": [
                    {
                        "from_user_id": "user_1@im.wechat",
                        "context_token": "ctx_token_123",
                        "item_list": [{"type": 1, "text_item": {"text": "你好"}}],
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    client = WechatIlinkClient(transport=transport)
    updates = await client.get_updates(bot_token="my_test_token", cursor="cursor_prev")  # noqa: S106

    assert len(requests_received) == 1
    assert updates["get_updates_buf"] == "cursor_next"
    assert len(updates["msgs"]) == 1


@pytest.mark.asyncio
async def test_send_message_chunking_and_context_token():
    sent_chunks = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/ilink/bot/sendmessage" in str(request.url)
        assert request.headers.get("Authorization") == "Bearer my_test_token"
        body = json.loads(request.read())
        msg = body["msg"]
        assert msg["to_user_id"] == "user_1@im.wechat"
        assert msg["context_token"] == "ctx_token_123"  # noqa: S105
        assert len(msg["client_id"]) >= 32  # valid UUID
        sent_chunks.append(msg["item_list"][0]["text_item"]["text"])
        return httpx.Response(200, json={"ret": 0})

    transport = httpx.MockTransport(handler)
    client = WechatIlinkClient(transport=transport)

    # 4500 chars -> chunks of 2000, 2000, 500
    long_text = "A" * 2000 + "B" * 2000 + "C" * 500
    success = await client.send_message(
        bot_token="my_test_token",  # noqa: S106
        to_user_id="user_1@im.wechat",
        context_token="ctx_token_123",  # noqa: S106
        text=long_text,
    )

    assert success is True
    assert len(sent_chunks) == 3
    assert len(sent_chunks[0]) == 2000
    assert len(sent_chunks[1]) == 2000
    assert len(sent_chunks[2]) == 500


@pytest.mark.asyncio
async def test_send_typing():
    typing_records = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/ilink/bot/sendtyping" in str(request.url)
        body = json.loads(request.read())
        typing_records.append(body)
        return httpx.Response(200, json={"ret": 0})

    transport = httpx.MockTransport(handler)
    client = WechatIlinkClient(transport=transport)

    await client.send_typing("my_token", "user_1", "ticket_123", start=True)
    await client.send_typing("my_token", "user_1", "ticket_123", start=False)

    assert len(typing_records) == 2
    assert typing_records[0]["status"] == 1
    assert typing_records[1]["status"] == 2
    assert typing_records[0]["typing_ticket"] == "ticket_123"
