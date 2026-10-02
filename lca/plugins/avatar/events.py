"""Avatar WS 推送通道（ADR-0269 §6）。

``AvatarEventPublisher`` 把 ``AvatarUpdatedEvent`` 发布到 Redis pub/sub
channel ``assistant_events:<assistant_id>``；``make_avatar_ws_handler``
生成 Starlette WebSocket 端点，订阅同一 channel 并把消息转发给前端。
WS 事件是投影通知，不承载状态（ADR-0269 §0 第 3 问）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from lca.contracts.models.avatar import AvatarUpdatedEvent
from lca.infrastructure.observability.stream.redis_client import (
    get_agent_runtime_redis_client,
)

logger = logging.getLogger(__name__)

EVENT_CHANNEL_PREFIX = "assistant_events:"
WS_PATH = "/v1/assistants/{id}/events"


class AvatarEventPublisher:
    """把 AvatarUpdatedEvent 发布到 Redis pub/sub（fire-and-forget）。

    ``publish`` 是同步入口（匹配 ``service.PublisherLike``），内部用
    ``asyncio.create_task`` 异步发布——调用方无需 await Redis。Redis 失败
    只记录日志，不破坏 avatar run（``set``/``clear``/视频完成照常返回）。
    """

    def __init__(self, redis: Any | None = None) -> None:
        self._redis = redis
        self._tasks: set[asyncio.Task[None]] = set()

    def _redis_client(self) -> Any:
        return self._redis or get_agent_runtime_redis_client()

    def publish(self, assistant_id: str, event: AvatarUpdatedEvent) -> None:
        try:
            task = asyncio.create_task(self._publish_async(assistant_id, event))
        except RuntimeError:
            # 没有运行中的事件循环（同步上下文）→ 放弃并记录，不向上抛。
            logger.exception(
                "avatar event publish skipped (no running loop) assistant_id=%s",
                assistant_id,
            )
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _publish_async(self, assistant_id: str, event: AvatarUpdatedEvent) -> None:
        channel = f"{EVENT_CHANNEL_PREFIX}{assistant_id}"
        try:
            await self._redis_client().publish(channel, event.model_dump_json())
        except Exception:
            logger.exception(
                "avatar event publish failed assistant_id=%s channel=%s",
                assistant_id,
                channel,
            )


def _authenticate(websocket: Any) -> str | None:
    """解析 WS 请求身份；失败返回 ``None``（调用方关闭 4401）。

    与 REST 路由同型（ADR-0252 D4）：Bearer token + ``x-lca-user-id``。
    WebSocket 也有 ``.headers`` / ``.app``，可直接鸭子类型传给 auth helper。
    """
    from lca.plugins.transport.webserver.handlers.auth.user import (
        auth_config_of,
        user_id_from_request,
    )

    expected_token, dev_mode = auth_config_of(websocket)
    user_id, error = user_id_from_request(
        websocket, expected_token=expected_token, dev_mode=dev_mode
    )
    if error is not None:
        return None
    return user_id


def _is_authorized(websocket: Any, user_id: str, assistant_id: str) -> bool:
    """归属校验（ADR-0252 D6）：非 owner 关闭 4404，不泄露存在性。"""
    from lca.plugins.transport.webserver.handlers.auth.user import auth_config_of

    _, dev_mode = auth_config_of(websocket)
    if dev_mode:
        return True
    app = getattr(websocket, "app", None)
    if app is None:
        return True
    state = getattr(app, "state", None)
    if state is None:
        return True
    ownership = getattr(state, "assistant_ownership", None)
    if ownership is None:
        return True
    owner = ownership.owner_of(assistant_id)
    return owner is not None and owner == user_id


def _service_exists(assistant_id: str) -> bool:
    """按 assistant_id 解析 avatar 服务；未注册返回 False（WS 关闭 4404）。"""
    from lca.plugins.avatar.registry import avatar_service_registry

    try:
        avatar_service_registry.get(assistant_id)
        return True
    except KeyError:
        return False


def make_avatar_ws_handler(redis: Any | None = None) -> Any:
    """返回 Starlette WebSocket 端点：订阅 ``assistant_events:<id>`` 并转发。

    ``redis`` 仅测试注入用；缺省走 ``get_agent_runtime_redis_client()``。
    """

    async def ws_endpoint(websocket: Any) -> None:
        from starlette.websockets import WebSocketDisconnect

        assistant_id = str(websocket.path_params["id"])
        await websocket.accept()

        user_id = _authenticate(websocket)
        if user_id is None:
            await websocket.close(code=4401)
            return
        if not _is_authorized(websocket, user_id, assistant_id):
            await websocket.close(code=4404)
            return
        if not _service_exists(assistant_id):
            await websocket.close(code=4404)
            return

        redis_client = redis or get_agent_runtime_redis_client()
        pubsub = redis_client.pubsub()
        channel = f"{EVENT_CHANNEL_PREFIX}{assistant_id}"
        try:
            await pubsub.subscribe(channel)
            await _forward_loop(websocket, pubsub)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("avatar events ws failed assistant_id=%s", assistant_id)
        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                logger.warning("avatar events ws unsubscribe failed assistant_id=%s", assistant_id)
            try:
                await pubsub.aclose()
            except Exception:
                logger.warning("avatar events ws aclose failed assistant_id=%s", assistant_id)

    return ws_endpoint


async def _forward_loop(websocket: Any, pubsub: Any) -> None:
    """转发 Redis pub/sub 消息，同时监听客户端断开。

    与 ``agent_gateway._live_loop`` 同型：``recv_task`` 与 ``msg_task``
    只重建已完成者，避免遗留孤儿任务；退出时统一 cancel+await 检索结果，
    防止 "Task exception was never retrieved" 告警。
    """
    from starlette.websockets import WebSocketDisconnect

    recv_task: asyncio.Task[Any] | None = None
    msg_task: asyncio.Task[Any] | None = None
    try:
        while True:
            if recv_task is None or recv_task.done():
                recv_task = asyncio.create_task(websocket.receive_text())
            if msg_task is None or msg_task.done():
                msg_task = asyncio.create_task(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
                )
            done, _pending = await asyncio.wait(
                {recv_task, msg_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if recv_task in done:
                try:
                    recv_task.result()
                except WebSocketDisconnect:
                    return
                except Exception:
                    # 未知 receive 失败按断开处理，避免空转。
                    return
                # 客户端发来文本：本通道只读推送，忽略并继续等待。
            if msg_task in done:
                message = await msg_task  # Redis 读失败上抛，由外层关闭连接
                if message is not None and message.get("type") == "message":
                    try:
                        await websocket.send_text(str(message["data"]))
                    except WebSocketDisconnect:
                        return
                msg_task = None
    finally:
        for task in (recv_task, msg_task):
            if task is None:
                continue
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


async def setup(ctx: Any, config: Any) -> None:
    """注册 avatar 事件 WS 路由（由 avatar 插件装配调用）。

    RouteSpec 只覆盖 HTTP；WebSocket 经 ``registry.register_websocket``
    挂载（同 ``routes_device.py``），dispose 走 ``ctx.effect`` 收口。
    """
    del config
    from starlette.routing import WebSocketRoute

    registry = ctx.require("route_registry")
    dispose = registry.register_websocket(WebSocketRoute(WS_PATH, make_avatar_ws_handler()))
    inner: Any = ctx._runtime()  # type: ignore[attr-defined]
    inner.effect(dispose, label=f"ws:{WS_PATH}")


__all__ = [
    "EVENT_CHANNEL_PREFIX",
    "WS_PATH",
    "AvatarEventPublisher",
    "make_avatar_ws_handler",
    "setup",
]
