"""Native Python client for Tencent WeChat iLink Bot API."""

from __future__ import annotations

import base64
import secrets
import uuid
from typing import Any

import httpx

from lca.contracts.channels.wechat import WechatQrResult, WechatStatusResult

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
CHANNEL_VERSION = "1.0.0"
MAX_TEXT_CHUNK_LENGTH = 2000
DEFAULT_TIMEOUT = 15.0
LONG_POLL_TIMEOUT = 45.0


def _random_uin() -> str:
    uint32 = secrets.randbelow(0xFFFFFFFF)
    return base64.b64encode(str(uint32).encode("ascii")).decode("ascii")


def _build_headers(bot_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {bot_token}",
        "AuthorizationType": "ilink_bot_token",
        "Content-Type": "application/json",
        "X-WECHAT-UIN": _random_uin(),
    }


def chunk_text(text: str, limit: int = MAX_TEXT_CHUNK_LENGTH) -> list[str]:
    """Split text into chunks up to limit characters."""
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    rem = text
    while rem:
        chunks.append(rem[:limit])
        rem = rem[limit:]
    return chunks


class WechatIlinkClient:
    """Async HTTP client for WeChat iLink Bot protocol."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
            headers={"User-Agent": "LCA-WechatClient/1.0"},
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def fetch_qrcode(self, bot_type: int = 3) -> WechatQrResult:
        """Fetch a new QR code for bot connection (unauthenticated)."""
        url = f"{self.base_url}/ilink/bot/get_bot_qrcode"
        resp = await self._client.get(url, params={"bot_type": str(bot_type)})
        resp.raise_for_status()
        data = resp.json()
        return WechatQrResult(
            qrcode=data["qrcode"],
            qrcode_img_content=data["qrcode_img_content"],
        )

    async def poll_qrcode_status(self, qrcode: str) -> WechatStatusResult:
        """Poll the QR code scan and confirmation status."""
        url = f"{self.base_url}/ilink/bot/get_qrcode_status"
        headers = {"iLink-App-ClientVersion": "1"}
        resp = await self._client.get(url, params={"qrcode": qrcode}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return WechatStatusResult(
            status=data.get("status", "wait"),
            bot_token=data.get("bot_token"),
            ilink_bot_id=data.get("ilink_bot_id"),
            ilink_user_id=data.get("ilink_user_id"),
            baseurl=data.get("baseurl"),
        )

    async def get_updates(
        self,
        bot_token: str,
        cursor: str = "",
        read_timeout: float = LONG_POLL_TIMEOUT,
    ) -> dict[str, Any]:
        """Long-poll WeChat iLink server for inbound messages (holds ~35s)."""
        url = f"{self.base_url}/ilink/bot/getupdates"
        body = {
            "base_info": {"channel_version": CHANNEL_VERSION},
            "get_updates_buf": cursor or "",
        }
        resp = await self._client.post(
            url,
            json=body,
            headers=_build_headers(bot_token),
            timeout=read_timeout,
        )
        resp.raise_for_status()
        return resp.json()

    async def send_message(
        self,
        bot_token: str,
        to_user_id: str,
        context_token: str,
        text: str,
    ) -> bool:
        """Send a text message chunked to 2000 chars via iLink sendmessage."""
        chunks = chunk_text(text, MAX_TEXT_CHUNK_LENGTH)
        if not chunks:
            return True

        url = f"{self.base_url}/ilink/bot/sendmessage"
        headers = _build_headers(bot_token)

        for chunk in chunks:
            body = {
                "base_info": {"channel_version": CHANNEL_VERSION},
                "msg": {
                    "client_id": str(uuid.uuid4()),
                    "context_token": context_token,
                    "from_user_id": "",
                    "to_user_id": to_user_id,
                    "message_state": 2,  # FINISH
                    "message_type": 1,  # BOT
                    "item_list": [{"type": 1, "text_item": {"text": chunk}}],
                },
            }
            resp = await self._client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("ret", 0) != 0:
                return False

        return True

    async def send_typing(
        self,
        bot_token: str,
        to_user_id: str,
        typing_ticket: str,
        start: bool = True,
    ) -> bool:
        """Send typing indicator (status: 1=start, 2=stop)."""
        url = f"{self.base_url}/ilink/bot/sendtyping"
        body = {
            "base_info": {"channel_version": CHANNEL_VERSION},
            "ilink_user_id": to_user_id,
            "status": 1 if start else 2,
            "typing_ticket": typing_ticket,
        }
        try:
            resp = await self._client.post(
                url,
                json=body,
                headers=_build_headers(bot_token),
            )
            return resp.is_success
        except Exception:
            return False
