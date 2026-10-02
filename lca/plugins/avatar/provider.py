"""grok2api 生图/视频 provider（ADR-0269 §3）。

瞬时错误（网络、429、5xx）指数退避重试最多 MAX_RETRIES 次；
确定性 4xx 不重试，直接向调用方抛 httpx.HTTPStatusError。
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal, Protocol, cast

import httpx
from pydantic import BaseModel, ConfigDict

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 2


class VideoStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    task_id: str
    state: Literal["pending", "running", "ready", "failed"]
    url: str | None = None


class AvatarImageProvider(Protocol):
    async def generate_image(
        self, prompt: str, reference_image_bytes: bytes | None = None
    ) -> bytes: ...
    async def create_video(self, image_bytes: bytes) -> str: ...
    async def get_video(self, task_id: str) -> VideoStatus: ...


class Grok2ApiProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        edit_model: str,
        video_model: str,
        _client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.edit_model = edit_model
        self.video_model = video_model
        self._client = _client or httpx.AsyncClient(base_url=self.base_url)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        data: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self._client.request(
                    method, path, headers=headers, json=json, files=files, data=data
                )
                if resp.status_code in RETRYABLE_STATUS:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError:
                raise
            except (httpx.HTTPError, httpx.TransportError) as exc:
                last_exc = exc
                await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"{method} {path} failed after {MAX_RETRIES + 1} attempts") from last_exc

    async def _post(
        self,
        path: str,
        *,
        json: dict[str, object] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        data: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        resp = await self._request("POST", path, json=json, files=files, data=data)
        return cast("dict[str, Any]", resp.json())

    async def _get(self, path: str) -> dict[str, Any]:
        resp = await self._request("GET", path)
        return cast("dict[str, Any]", resp.json())

    async def _download(self, url: str) -> bytes:
        """下载生成结果；文件端点无需鉴权，故不携带 Authorization。

        下载失败（网络、5xx）仍按瞬时错误指数退避重试。
        """
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self._client.get(url)
                if resp.status_code in RETRYABLE_STATUS:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                resp.raise_for_status()
                return resp.content
            except httpx.HTTPStatusError:
                raise
            except (httpx.HTTPError, httpx.TransportError) as exc:
                last_exc = exc
                await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"GET {url} failed after {MAX_RETRIES + 1} attempts") from last_exc

    async def generate_image(
        self, prompt: str, reference_image_bytes: bytes | None = None
    ) -> bytes:
        if reference_image_bytes is None:
            data = await self._post(
                "/images/generations",
                json={"model": self.model, "prompt": prompt, "n": 1},
            )
        else:
            data = await self._post(
                "/images/edits",
                files={"image": ("avatar.png", reference_image_bytes, "image/png")},
                data={"model": self.edit_model, "prompt": prompt},
            )
        url = data["data"][0]["url"]
        return await self._download(url)

    async def create_video(self, image_bytes: bytes) -> str:
        data = await self._post(
            "/videos",
            files={"image": ("avatar.png", image_bytes, "image/png")},
            data={"model": self.video_model},
        )
        return str(data["id"])

    async def get_video(self, task_id: str) -> VideoStatus:
        data = await self._get(f"/videos/{task_id}")
        state = data.get("status", "pending")
        return VideoStatus(
            task_id=task_id,
            state=state if state in {"pending", "running", "ready", "failed"} else "pending",
            url=data.get("url"),
        )
