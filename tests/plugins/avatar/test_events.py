"""Avatar WS 推送通道测试（Task 7 + gateway 风格首帧 JWT 鉴权 fix）。

覆盖：
- AvatarEventPublisher.publish 经 Redis pub/sub 发布 AvatarUpdatedEvent JSON（fake redis）；
- publish 是 fire-and-forget：Redis 失败只记日志，不破坏调用方；
- WS handler：dev_mode 下无需 token 直接进入订阅转发（header 鉴权回退）；
- WS handler：非 dev_mode 首帧 JWT 握手——有效 token 放行，无效 token / 非 auth
  帧关闭 4401，非 owner 关闭 4404；
- 客户端断开后清理 pubsub（unsubscribe + aclose）；
- events.setup 经 registry.register_websocket 挂载 /v1/assistants/{id}/events。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.websockets import WebSocketDisconnect

from lca.contracts.models.avatar import AvatarUpdatedEvent
from lca.plugins.avatar.events import AvatarEventPublisher, make_avatar_ws_handler
from lca.plugins.avatar.registry import avatar_service_registry
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    mint_user_jwt,
)
from lca.plugins.transport.webserver.router.router import RouteRegistry


@pytest.fixture(scope="module")
def rsa_keys() -> dict[str, str]:
    """模块级 RSA 密钥对，供 JWT mint/verify 测试使用。"""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return {"private": private_pem, "public": public_pem}


class _RecordingRedis:
    """只记录 publish 调用的假 redis。"""

    def __init__(self) -> None:
        self.sent: dict[str, str] = {}

    async def publish(self, channel: str, message: str) -> None:
        self.sent[channel] = message


class _FailingRedis:
    """publish 总是失败的假 redis。"""

    async def publish(self, channel: str, message: str) -> None:
        raise ConnectionError("redis down")


class _FakePubSub:
    def __init__(self, messages: list[dict[str, Any]] | None = None) -> None:
        self.messages = list(messages or [])
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False
        self._blocker = asyncio.Event()
        self._index = 0

    async def subscribe(self, *channels: str) -> None:
        self.subscribed.extend(channels)

    async def get_message(
        self,
        ignore_subscribe_messages: bool = True,
        timeout: float = 30,  # noqa: ASYNC109 — 镜像 redis.asyncio.PubSub.get_message 签名
    ) -> dict[str, Any] | None:
        if self._index < len(self.messages):
            message = self.messages[self._index]
            self._index += 1
            return message
        await self._blocker.wait()
        return None

    async def unsubscribe(self, *channels: str) -> None:
        self.unsubscribed.extend(channels)

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedis:
    def __init__(self, pubsub: _FakePubSub) -> None:
        self._pubsub = pubsub

    def pubsub(self) -> _FakePubSub:
        return self._pubsub


class _FakeOwnership:
    def __init__(self, owner_map: dict[str, str]) -> None:
        self._owner_map = owner_map

    def owner_of(self, assistant_id: str) -> str | None:
        return self._owner_map.get(assistant_id)


class _FakeWebSocket:
    def __init__(self, assistant_id: str, recv_texts: list[str] | None = None) -> None:
        self.path_params = {"id": assistant_id}
        self.headers: dict[str, str] = {}
        self.app: Any = None
        self.accepted = False
        self.sent: list[str] = []
        self.close_code: int | None = None
        self._recv_texts = list(recv_texts or [])
        self._recv_index = 0
        self._disconnect = asyncio.Event()

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def send_json(self, data: Any) -> None:
        self.sent.append(json.dumps(data))

    async def receive_text(self) -> str:
        if self._recv_index < len(self._recv_texts):
            text = self._recv_texts[self._recv_index]
            self._recv_index += 1
            return text
        await self._disconnect.wait()
        raise WebSocketDisconnect(1000, "")

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.close_code = code


class _FakeRuntime:
    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    def __init__(self, router: RouteRegistry) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()

    def require(self, key: str) -> Any:
        assert key == "route_registry"
        return self._router

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    avatar_service_registry.clear()
    yield
    avatar_service_registry.clear()


# ── AvatarEventPublisher ────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_event_roundtrip() -> None:
    redis = _RecordingRedis()
    publisher = AvatarEventPublisher(redis=redis)
    publisher.publish(
        "asst_1",
        AvatarUpdatedEvent(type="avatar_updated", assistant_id="asst_1", payload={"x": 1}),
    )
    # fire-and-forget：调用返回时尚未执行 Redis 写。
    assert redis.sent == {}
    for _ in range(10):
        if redis.sent:
            break
        await asyncio.sleep(0)
    assert "assistant_events:asst_1" in redis.sent
    data = json.loads(redis.sent["assistant_events:asst_1"])
    assert data["type"] == "avatar_updated"
    assert data["assistant_id"] == "asst_1"
    assert data["payload"] == {"x": 1}


@pytest.mark.asyncio
async def test_publish_redis_failure_is_swallowed(caplog) -> None:
    publisher = AvatarEventPublisher(redis=_FailingRedis())
    publisher.publish(
        "asst_1",
        AvatarUpdatedEvent(type="avatar_updated", assistant_id="asst_1", payload={}),
    )
    for _ in range(10):
        await asyncio.sleep(0)
    # Redis 失败不得上抛：只记录日志。
    assert any("avatar event publish failed" in record.message for record in caplog.records)


# ── WS handler：dev_mode（无需 token） ───────────────────────────


@pytest.mark.asyncio
async def test_ws_handler_dev_mode_no_token_proceeds() -> None:
    """dev_mode：不要求 JWT，header 鉴权回退路径可用，直接订阅转发。"""
    assistant_id = "asst_ws_1"
    avatar_service_registry.register(assistant_id, object())
    event = AvatarUpdatedEvent(
        type="avatar_updated", assistant_id=assistant_id, payload={"ok": True}
    )
    pubsub = _FakePubSub(messages=[{"type": "message", "data": event.model_dump_json()}])
    redis = _FakeRedis(pubsub)
    ws = _FakeWebSocket(assistant_id=assistant_id)
    ws.headers = {"x-lca-user-id": "local-dev-user"}  # header 回退路径

    handler = make_avatar_ws_handler(redis=redis)
    task = asyncio.create_task(handler(ws))
    for _ in range(50):
        if ws.sent:
            break
        await asyncio.sleep(0)
    assert ws.accepted is True
    assert pubsub.subscribed == [f"assistant_events:{assistant_id}"]
    assert len(ws.sent) == 1
    assert json.loads(ws.sent[0])["type"] == "avatar_updated"

    # 客户端断开 → 循环退出并清理 pubsub。
    ws._disconnect.set()
    await asyncio.wait_for(task, timeout=1)
    assert pubsub.closed is True
    assert f"assistant_events:{assistant_id}" in pubsub.unsubscribed


@pytest.mark.asyncio
async def test_ws_handler_unknown_assistant_closes_4404() -> None:
    ws = _FakeWebSocket(assistant_id="asst_missing")
    handler = make_avatar_ws_handler(redis=_FakeRedis(_FakePubSub()))
    await handler(ws)
    assert ws.accepted is True
    assert ws.close_code == 4404


# ── WS handler：非 dev_mode（首帧 JWT 握手） ────────────────────


@pytest.mark.asyncio
async def test_ws_handler_invalid_token_frame_closes_4401(rsa_keys: dict[str, str]) -> None:
    ws = _FakeWebSocket(
        assistant_id="asst_auth",
        recv_texts=['{"type":"auth","token":"not.a.jwt"}'],
    )
    ws.app = SimpleNamespace(
        state=SimpleNamespace(
            lca_auth_dev_mode=False,
            lca_auth_expected_token="test-token",  # noqa: S106  # 测试专用
            jwt_keys=SimpleNamespace(public_pem=rsa_keys["public"]),
        )
    )
    handler = make_avatar_ws_handler(redis=_FakeRedis(_FakePubSub()))
    await handler(ws)
    assert ws.accepted is True
    assert ws.close_code == 4401
    assert any("auth_failed" in message for message in ws.sent)


@pytest.mark.asyncio
async def test_ws_handler_non_auth_first_frame_closes_4401(rsa_keys: dict[str, str]) -> None:
    ws = _FakeWebSocket(
        assistant_id="asst_badframe",
        recv_texts=['{"type":"hello"}'],
    )
    ws.app = SimpleNamespace(
        state=SimpleNamespace(
            lca_auth_dev_mode=False,
            lca_auth_expected_token="test-token",  # noqa: S106  # 测试专用
            jwt_keys=SimpleNamespace(public_pem=rsa_keys["public"]),
        )
    )
    handler = make_avatar_ws_handler(redis=_FakeRedis(_FakePubSub()))
    await handler(ws)
    assert ws.close_code == 4401


@pytest.mark.asyncio
async def test_ws_handler_valid_jwt_frame_proceeds(rsa_keys: dict[str, str]) -> None:
    assistant_id = "asst_jwt_ok"
    avatar_service_registry.register(assistant_id, object())
    token = mint_user_jwt(
        user_id="alice",
        operation_id=assistant_id,
        private_key_pem=rsa_keys["private"],
    )
    ws = _FakeWebSocket(
        assistant_id=assistant_id,
        recv_texts=[json.dumps({"type": "auth", "token": token})],
    )
    ws.app = SimpleNamespace(
        state=SimpleNamespace(
            lca_auth_dev_mode=False,
            lca_auth_expected_token="test-token",  # noqa: S106  # 测试专用
            jwt_keys=SimpleNamespace(public_pem=rsa_keys["public"]),
        )
    )
    event = AvatarUpdatedEvent(
        type="avatar_updated", assistant_id=assistant_id, payload={"ok": True}
    )
    pubsub = _FakePubSub(messages=[{"type": "message", "data": event.model_dump_json()}])
    redis = _FakeRedis(pubsub)

    handler = make_avatar_ws_handler(redis=redis)
    task = asyncio.create_task(handler(ws))
    for _ in range(50):
        if any("avatar_updated" in message for message in ws.sent):
            break
        await asyncio.sleep(0)
    assert ws.accepted is True
    assert pubsub.subscribed == [f"assistant_events:{assistant_id}"]
    assert any("avatar_updated" in message for message in ws.sent)

    ws._disconnect.set()
    await asyncio.wait_for(task, timeout=1)
    assert pubsub.closed is True


@pytest.mark.asyncio
async def test_ws_handler_jwt_user_not_owner_closes_4404(rsa_keys: dict[str, str]) -> None:
    assistant_id = "asst_owner"
    avatar_service_registry.register(assistant_id, object())
    token = mint_user_jwt(
        user_id="alice",
        operation_id=assistant_id,
        private_key_pem=rsa_keys["private"],
    )
    ws = _FakeWebSocket(
        assistant_id=assistant_id,
        recv_texts=[json.dumps({"type": "auth", "token": token})],
    )
    ws.app = SimpleNamespace(
        state=SimpleNamespace(
            lca_auth_dev_mode=False,
            lca_auth_expected_token="test-token",  # noqa: S106  # 测试专用
            assistant_ownership=_FakeOwnership({assistant_id: "bob"}),
            jwt_keys=SimpleNamespace(public_pem=rsa_keys["public"]),
        )
    )
    handler = make_avatar_ws_handler(redis=_FakeRedis(_FakePubSub()))
    await handler(ws)
    assert ws.accepted is True
    assert ws.close_code == 4404


# ── setup 挂载 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ws_setup_registers_websocket_route() -> None:
    from lca.plugins.avatar.events import setup

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await setup(ctx, None)
    app = Starlette()
    router.install(app)
    paths = [getattr(route, "path", None) for route in app.routes]
    assert "/v1/assistants/{id}/events" in paths
