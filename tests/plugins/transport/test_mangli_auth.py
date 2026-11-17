"""Tests for Mangli enterprise authentication, Principal model, and smart adaptive auth middleware."""

import pytest

from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
    ExpiringLruCache,
    MangliAuthService,
    PermissionServiceUnavailableError,
    SmartAdaptiveAuthMiddleware,
    decrypt_mangli_user_header,
    derive_sha1prng_key,
    encrypt_mangli_user_header_for_test,
    get_current_principal,
)
from lca.plugins.transport.webserver.handlers.auth.principal import Principal


def test_java_cross_compatibility_vector():
    key_hex = "0123456789abcdef0123456789abcdef"
    key = bytes.fromhex(key_hex)
    expected_cipher_hex = "39b8a117fb5afc5bde07945964f2c2b8bb1fdd7c43d44d40336c864cbf7accea01c34f86851bc289a5acd8e9d953c24cdff6f07e6a20d89b8f5fde7ca6eab628"

    info = decrypt_mangli_user_header(expected_cipher_hex, key)
    assert info["user_id"] == "U888"
    assert info["name"] == "zhangsan"
    assert info["dept_id"] == "D01"

    re_enc = encrypt_mangli_user_header_for_test(
        '{"user_id":"U888","name":"zhangsan","dept_id":"D01"}', key
    )
    assert re_enc == expected_cipher_hex


def test_sha1prng_fallback_derivation():
    password = b"mangli_test_key_2026"
    key = derive_sha1prng_key(password)
    assert len(key) == 16


def test_expiring_lru_cache_standard_library():
    cache = ExpiringLruCache(maxsize=10, ttl_seconds=1)
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1"
    assert cache.get("k2") is None


@pytest.mark.asyncio
async def test_permission_cache_ttl_and_error_handling():
    call_count = 0

    async def mock_fetch_permissions(ticket: str, user_id: str):
        nonlocal call_count
        call_count += 1
        if ticket == "invalid":
            raise ValueError("invalid ticket")
        if ticket == "down":
            raise PermissionServiceUnavailableError("service timeout")
        return ["user:read", "project:access"], ["engineer"]

    service = MangliAuthService(fetch_fn=mock_fetch_permissions)
    perms, roles = await service.get_permissions("ticket_123", "U1001")
    assert call_count == 1
    assert "user:read" in perms
    assert "engineer" in roles

    # 命中 5min 缓存
    perms2, roles2 = await service.get_permissions("ticket_123", "U1001")
    assert call_count == 1
    assert perms2 == perms
    assert roles2 == roles

    # Fail-Closed 异常阻断
    with pytest.raises(PermissionServiceUnavailableError):
        await service.get_permissions("down", "U1002")


@pytest.mark.asyncio
async def test_adaptive_auth_double_track():
    captured_headers = {}
    captured_principal = None

    async def dummy_app(scope, receive, send):
        nonlocal captured_headers, captured_principal
        captured_headers = dict(scope.get("headers", []))
        captured_principal = get_current_principal()

    class FakeAppState:
        lca_auth_expected_token = "secret-token-123"  # noqa: S105
        lca_auth_dev_mode = False

    class FakeApp:
        state = FakeAppState()

    mw = SmartAdaptiveAuthMiddleware(dummy_app)

    # 1. 带有伪造头的公司 Gateway 流量：验证解密、剥离伪造头并注入合法 Bearer
    key = bytes.fromhex("0123456789abcdef0123456789abcdef")
    enc = encrypt_mangli_user_header_for_test(
        '{"user_id":"U888","name":"zhangsan","dept_id":"D01"}', key
    )
    scope_gateway = {
        "type": "http",
        "path": "/runs",
        "app": FakeApp(),
        "headers": [
            (b"x-mangli-user", enc.encode()),
            (b"ticket", b"t123"),
            (b"x-lca-user-id", b"malicious_spoofed_id"),  # 伪造头
            (b"authorization", b"Bearer fake"),  # 伪造 Token
        ],
    }
    await mw(scope_gateway, None, None)
    # 验证伪造头被彻底剔除，真实工号生效
    assert captured_headers.get(b"x-lca-user-id") == b"U888"
    assert (
        captured_headers.get(b"authorization") == b"Bearer secret-token-123"
    )
    assert isinstance(captured_principal, Principal)
    assert captured_principal.issuer == "mangli"
    assert captured_principal.subject == "U888"


@pytest.mark.asyncio
async def test_unauthenticated_traffic_rejected_when_prod_mode():
    sent_messages = []

    async def dummy_app(scope, receive, send):
        pass

    async def mock_send(message):
        sent_messages.append(message)

    class FakeAppState:
        lca_auth_expected_token = "secret-token-123"  # noqa: S105
        lca_auth_dev_mode = False

    class FakeApp:
        state = FakeAppState()

    mw = SmartAdaptiveAuthMiddleware(dummy_app)
    # 生产模式下未带网关头且未带合法 Bearer 的请求必须直接被 401 拦截
    scope_unauth = {
        "type": "http",
        "path": "/runs",
        "app": FakeApp(),
        "headers": [(b"x-lca-user-id", b"intruder")],
    }
    await mw(scope_unauth, None, mock_send)
    assert len(sent_messages) >= 1
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 401


@pytest.mark.asyncio
async def test_adaptive_auth_decryption_failure_returns_401():
    sent_messages = []

    async def dummy_app(scope, receive, send):
        pass

    async def mock_send(message):
        sent_messages.append(message)

    class FakeAppState:
        lca_auth_expected_token = "secret-token-123"  # noqa: S105
        lca_auth_dev_mode = False

    class FakeApp:
        state = FakeAppState()

    mw = SmartAdaptiveAuthMiddleware(dummy_app)
    scope_bad_cipher = {
        "type": "http",
        "path": "/runs",
        "app": FakeApp(),
        "headers": [
            (b"x-mangli-user", b"not_valid_hex_or_bad_padding"),
        ],
    }
    await mw(scope_bad_cipher, None, mock_send)
    assert len(sent_messages) >= 1
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 401


@pytest.mark.asyncio
async def test_adaptive_auth_invalid_ticket_returns_401():
    sent_messages = []

    async def dummy_app(scope, receive, send):
        pass

    async def mock_send(message):
        sent_messages.append(message)

    async def mock_fetch_invalid(ticket: str, user_id: str):
        raise ValueError("invalid ticket")

    class FakeAppState:
        lca_auth_expected_token = "secret-token-123"  # noqa: S105
        lca_auth_dev_mode = False

    class FakeApp:
        state = FakeAppState()

    service = MangliAuthService(fetch_fn=mock_fetch_invalid)
    mw = SmartAdaptiveAuthMiddleware(dummy_app, auth_service=service)

    key = bytes.fromhex("0123456789abcdef0123456789abcdef")
    enc = encrypt_mangli_user_header_for_test(
        '{"user_id":"U888","name":"zhangsan","dept_id":"D01"}', key
    )
    scope_invalid_ticket = {
        "type": "http",
        "path": "/runs",
        "app": FakeApp(),
        "headers": [
            (b"x-mangli-user", enc.encode()),
            (b"ticket", b"bad_ticket"),
        ],
    }
    await mw(scope_invalid_ticket, None, mock_send)
    assert len(sent_messages) >= 1
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 401
