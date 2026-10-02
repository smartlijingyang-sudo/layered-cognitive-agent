"""Grok2ApiProvider 生图/视频 HTTP 客户端测试（Task 3）。

用 httpx.MockTransport 桩掉上游 grok2api 代理，覆盖：
- 文生图 / 图生图 / 视频创建 / 视频状态轮询；
- 瞬时错误（5xx/429/传输异常）指数退避重试；
- 确定性 4xx 不重试直接抛错；
- 下载失败按瞬时错误重试。
"""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient, MockTransport, Request, Response

from lca.plugins.avatar.provider import Grok2ApiProvider, VideoStatus


def _provider(handler) -> Grok2ApiProvider:
    return Grok2ApiProvider(
        base_url="http://test/v1",
        api_key="k",
        model="m",
        edit_model="em",
        video_model="vm",
        _client=AsyncClient(transport=MockTransport(handler), base_url="http://test/v1"),
    )


@pytest.mark.asyncio
async def test_generate_image_returns_bytes():
    calls = {"download": 0}

    def handler(request: Request) -> Response:
        if request.url.path == "/v1/images/generations":
            return Response(200, json={"data": [{"url": "http://test/img.png"}]})
        calls["download"] += 1
        return Response(200, content=b"PNG")

    provider = _provider(handler)
    assert await provider.generate_image("hello") == b"PNG"
    assert calls["download"] == 1


@pytest.mark.asyncio
async def test_generate_image_with_reference_uses_edits():
    seen = {}

    def handler(request: Request) -> Response:
        if request.url.path == "/v1/images/edits":
            seen["path"] = request.url.path
            return Response(200, json={"data": [{"url": "http://test/edited.png"}]})
        return Response(200, content=b"EDITED")

    provider = _provider(handler)
    assert await provider.generate_image("edit it", reference_image_bytes=b"ref") == b"EDITED"
    assert seen["path"] == "/v1/images/edits"


@pytest.mark.asyncio
async def test_retry_on_5xx_then_success():
    n = {"count": 0}

    def handler(request: Request) -> Response:
        n["count"] += 1
        if request.url.path == "/v1/images/generations":
            if n["count"] == 1:
                return Response(500)
            return Response(200, json={"data": [{"url": "http://test/x.png"}]})
        return Response(200, content=b"PNG")

    provider = _provider(handler)
    assert await provider.generate_image("x") == b"PNG"
    assert n["count"] >= 2


@pytest.mark.asyncio
async def test_retry_on_429_then_success():
    n = {"count": 0}

    def handler(request: Request) -> Response:
        n["count"] += 1
        if request.url.path == "/v1/images/generations":
            if n["count"] == 1:
                return Response(429)
            return Response(200, json={"data": [{"url": "http://test/x.png"}]})
        return Response(200, content=b"PNG")

    provider = _provider(handler)
    assert await provider.generate_image("x") == b"PNG"
    assert n["count"] >= 2


@pytest.mark.asyncio
async def test_retry_on_transport_error_then_success():
    n = {"count": 0}

    def handler(request: Request) -> Response:
        n["count"] += 1
        if request.url.path == "/v1/images/generations":
            if n["count"] == 1:
                raise httpx.ConnectError("connection refused")
            return Response(200, json={"data": [{"url": "http://test/x.png"}]})
        return Response(200, content=b"PNG")

    provider = _provider(handler)
    assert await provider.generate_image("x") == b"PNG"
    assert n["count"] >= 2


@pytest.mark.asyncio
async def test_generate_image_4xx_raises_without_retry():
    n = {"count": 0}

    def handler(request: Request) -> Response:
        n["count"] += 1
        return Response(400, json={"error": "bad request"})

    provider = _provider(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await provider.generate_image("x")
    assert n["count"] == 1


@pytest.mark.asyncio
async def test_download_retries_on_5xx():
    n = {"count": 0}

    def handler(request: Request) -> Response:
        if request.url.path == "/v1/images/generations":
            return Response(200, json={"data": [{"url": "http://test/x.png"}]})
        n["count"] += 1
        if n["count"] == 1:
            return Response(500)
        return Response(200, content=b"PNG")

    provider = _provider(handler)
    assert await provider.generate_image("x") == b"PNG"
    assert n["count"] == 2


@pytest.mark.asyncio
async def test_create_video_returns_task_id():
    def handler(request: Request) -> Response:
        assert request.url.path == "/v1/videos"
        return Response(200, json={"id": "task_1"})

    provider = _provider(handler)
    assert await provider.create_video(b"png-bytes") == "task_1"


@pytest.mark.asyncio
async def test_get_video_uses_get_and_returns_status():
    seen: dict[str, str | None] = {"method": None}

    def handler(request: Request) -> Response:
        seen["method"] = request.method
        assert request.url.path == "/v1/videos/task_1"
        return Response(200, json={"status": "ready", "url": "http://test/video.mp4"})

    provider = _provider(handler)
    status = await provider.get_video("task_1")
    assert seen["method"] == "GET"
    assert status == VideoStatus(task_id="task_1", state="ready", url="http://test/video.mp4")


@pytest.mark.asyncio
async def test_get_video_maps_unknown_status_to_pending():
    def handler(request: Request) -> Response:
        return Response(200, json={"status": "weird", "url": "http://test/video.mp4"})

    provider = _provider(handler)
    status = await provider.get_video("task_1")
    assert status.state == "pending"
    assert status.url == "http://test/video.mp4"
