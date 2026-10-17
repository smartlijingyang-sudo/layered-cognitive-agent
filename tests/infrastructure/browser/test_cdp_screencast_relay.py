"""Tests for CDPScreencastRelay and BrowserDriverPort (INV-BROWSER-04)."""

from unittest.mock import AsyncMock

import pytest

from lca.contracts.models.browser.stream import BrowserSessionStatus
from lca.infrastructure.browser.screencast_relay import CDPScreencastRelay


@pytest.mark.asyncio
async def test_relay_encodes_binary_frame_with_0x01_header() -> None:
    mock_ws = AsyncMock()
    relay = CDPScreencastRelay(session_id="test_sess_01")
    relay.register_client(mock_ws)

    jpeg_bytes = b"\xff\xd8\xff\xe0testjpegimagecontent"
    await relay.emit_frame(data=jpeg_bytes, metadata={"width": 1280, "height": 800})

    assert mock_ws.send_bytes.called
    sent_payload = mock_ws.send_bytes.call_args[0][0]
    assert sent_payload[0] == 0x01  # INV-BROWSER-04: 二进制首字节帧类型
    assert sent_payload[1:] == jpeg_bytes


@pytest.mark.asyncio
async def test_relay_json_metadata_and_status_frames() -> None:
    mock_ws = AsyncMock()
    relay = CDPScreencastRelay(session_id="test_sess_02")
    relay.register_client(mock_ws)

    await relay.emit_status(BrowserSessionStatus.HUMAN_TAKEOVER)
    assert mock_ws.send_json.called
    payload = mock_ws.send_json.call_args[0][0]
    assert payload["type"] == "status"
    assert payload["status"] == "human_takeover"


@pytest.mark.asyncio
async def test_relay_backpressure_throttling() -> None:
    mock_ws = AsyncMock()
    relay = CDPScreencastRelay(session_id="test_sess_03", max_in_flight=2)
    relay.register_client(mock_ws)

    data = b"\xff\xd8\xff\xe0sample"
    # 第 1 帧
    sent1 = await relay.emit_frame(data)
    assert sent1 is True
    # 第 2 帧
    sent2 = await relay.emit_frame(data)
    assert sent2 is True
    # 第 3 帧超过 max_in_flight=2，应该被丢弃节流保护
    sent3 = await relay.emit_frame(data)
    assert sent3 is False

    # 收到 ACK 后恢复
    relay.handle_ack()
    sent4 = await relay.emit_frame(data)
    assert sent4 is True


@pytest.mark.asyncio
async def test_relay_cleanup_on_close() -> None:
    mock_ws = AsyncMock()
    relay = CDPScreencastRelay(session_id="test_sess_04")
    relay.register_client(mock_ws)
    assert relay.client_count == 1

    await relay.close()
    assert relay.client_count == 0
    assert mock_ws.close.called
