"""Tests for Mangli enterprise authentication, Principal model, and smart adaptive auth middleware."""

import pytest

from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
    DEFAULT_AES_KEY,
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


async def _allow_all(ticket: str, user_id: str) -> tuple[list[str], list[str]]:
    """测试替身：显式注入"票有效"，代替已删除的生产默认放行。"""
    return ["user:read"], ["user"]


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

    key = bytes.fromhex("0123456789abcdef0123456789abcdef")
    # aes_key 与 ticket 校验器必须显式注入：生产默认值已改为 fail-closed。
    mw = SmartAdaptiveAuthMiddleware(
        dummy_app, auth_service=MangliAuthService(fetch_fn=_allow_all), aes_key=key
    )

    # 1. 带有伪造头的公司 Gateway 流量：验证解密、剥离伪造头并注入合法 Bearer
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

    mw = SmartAdaptiveAuthMiddleware(dummy_app, aes_key=DEFAULT_AES_KEY)
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

    key = bytes.fromhex("0123456789abcdef0123456789abcdef")
    service = MangliAuthService(fetch_fn=mock_fetch_invalid)
    mw = SmartAdaptiveAuthMiddleware(dummy_app, auth_service=service, aes_key=key)

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


@pytest.mark.asyncio
async def test_java_user_principal_9_fields_and_embedded_ticket():
    captured_principal = None

    async def dummy_app(scope, receive, send):
        nonlocal captured_principal
        captured_principal = get_current_principal()

    class FakeAppState:
        lca_auth_expected_token = "secret-token-123"  # noqa: S105
        lca_auth_dev_mode = False

    class FakeApp:
        state = FakeAppState()

    key = bytes.fromhex("0123456789abcdef0123456789abcdef")
    mw = SmartAdaptiveAuthMiddleware(
        dummy_app, auth_service=MangliAuthService(fetch_fn=_allow_all), aes_key=key
    )

    # 模拟真实 Java Spring Cloud Gateway 传出的 UserPrincipal JSON
    import json
    gateway_payload = {
        "userId": "10001",
        "name": "李四",
        "mobile": "13912345678",
        "email": "lisi@mangli.com",
        "jobNumber": "E9999",
        "jobName": "资深开发",
        "department": "平台架构部",
        "clockInType": 1,
        "ticket": "TKT-EMBEDDED-VALID",
    }
    cipher_hex = encrypt_mangli_user_header_for_test(json.dumps(gateway_payload), key)

    scope_gateway = {
        "type": "http",
        "path": "/runs",
        "app": FakeApp(),
        "headers": [
            (b"x-mangli-user", cipher_hex.encode()),
        ],
    }
    await mw(scope_gateway, None, None)

    assert isinstance(captured_principal, Principal)
    assert captured_principal.issuer == "mangli"
    assert captured_principal.subject == "10001"
    assert captured_principal.user_id == "10001"
    assert captured_principal.name == "李四"
    assert captured_principal.mobile == "13912345678"
    assert captured_principal.email == "lisi@mangli.com"
    assert captured_principal.job_number == "E9999"
    assert captured_principal.job_name == "资深开发"
    assert captured_principal.department == "平台架构部"
    assert captured_principal.clock_in_type == 1
    assert captured_principal.ticket == "TKT-EMBEDDED-VALID"


def test_get_configured_aes_key_resolution(monkeypatch):
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import get_configured_aes_key

    # 1. 未配置 env → 没有密钥，绝不回落到公开默认值
    monkeypatch.delenv("MANGLI_AUTH_AES_KEY", raising=False)
    assert get_configured_aes_key() is None

    # 2. 32 位 Hex 密钥
    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "fedcba9876543210fedcba9876543210")
    assert get_configured_aes_key() == bytes.fromhex("fedcba9876543210fedcba9876543210")

    # 3. 密码字符串 (走 SHA1PRNG 派生)
    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "custom_gateway_password")
    assert get_configured_aes_key() == derive_sha1prng_key(b"custom_gateway_password")

    # 4. AES-256：64 位 Hex 必须当成 32 字节密钥，不能掉进 SHA1PRNG 派生出另一把
    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "ab" * 32)
    assert get_configured_aes_key() == b"\xab" * 32

    # 5. AES-192：48 位 Hex → 24 字节
    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "cd" * 24)
    assert get_configured_aes_key() == b"\xcd" * 24

    # 6. 32 字节原文密钥（非 Hex 字符）
    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "x" * 32)
    assert get_configured_aes_key() == b"x" * 32


def test_sha1prng_derivation_matches_java_keygenerator_vector() -> None:
    """真值由与网关加密源码等价的 Java 程序产出（JDK 8u261 与 JDK 21 结果一致）。

    网关侧::

        SecureRandom r = SecureRandom.getInstance("SHA1PRNG");
        r.setSeed(password.getBytes());
        KeyGenerator kgen = KeyGenerator.getInstance("AES");
        kgen.init(128, r);
        Cipher.getInstance("AES/ECB/PKCS5Padding").doFinal(json)

    派生是 ``SHA1(SHA1(seed))[:16]``；旧实现算 ``SHA1(seed)[:16]``，导致
    所有走密码派生的网关流量永远 401（本用例即该 bug 的回归锁）。
    """
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
        decrypt_mangli_user_header,
        derive_sha1prng_key,
    )

    # (password, java key hex, java cipher hex of {"userId":"10001"})
    vectors = [
        (
            b"mangli-secret",
            "3baeb6bd8ac53998aa6342e9f8bd2ab2",
            "b6ec44745ab27cecd4f068d10537bfedc9ae8a7c533771f848af221dbd11ad9e",
        ),
        (
            b"Mangli2026Key!",
            "b978c5d1ba87145c43b8a8e0672085c7",
            "b62960a430bee910e5e342212fc123332f54d138b4101791bdf25565f4f532ad",
        ),
        (
            b"company_gateway_password",
            "3b7b7bd8bee126e7dea63dacb5ac9741",
            "6483ad3dc71850b06884f343c7b38b42fbf6a092cce2c67fa44c2530303aab71",
        ),
    ]
    for password, key_hex, cipher_hex in vectors:
        assert derive_sha1prng_key(password).hex() == key_hex
        # 端到端：Java 加出来的密文，服务端必须能解开
        assert decrypt_mangli_user_header(cipher_hex, key=bytes.fromhex(key_hex))["userId"] == "10001"


def test_password_env_follows_java_sha1prng(monkeypatch) -> None:
    """``MANGLI_AUTH_AES_KEY`` 填密码时，服务端必须按 Java 口径派生成网关那把密钥。"""
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import get_configured_aes_key

    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "mangli-secret")
    assert (
        get_configured_aes_key().hex() == "3baeb6bd8ac53998aa6342e9f8bd2ab2"
    ), "密码派生必须等于 Java KeyGenerator(SHA1PRNG) 产出的密钥"


def test_describe_configured_aes_key_reports_interpretation(monkeypatch):
    """诊断必须能说清"服务端把你的值当成了什么"，否则长度不对时无从发现。"""
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
        describe_configured_aes_key,
    )

    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "fedcba9876543210fedcba9876543210")
    info = describe_configured_aes_key()
    assert info["interpreted_as"] == "env_hex"
    assert info["key_bits"] == 128
    assert info["env_value_len"] == 32

    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "0123456789abcdeZ")  # 16 字节原文
    info = describe_configured_aes_key()
    assert info["interpreted_as"] == "env_text"
    assert info["env_value_len"] == 16

    # 长度不合法的密码 → 服务端只能 SHA1PRNG 派生，长度本身即诊断事实
    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "mangli-secret")
    info = describe_configured_aes_key()
    assert info["interpreted_as"] == "sha1prng"
    assert info["env_value_len"] == len("mangli-secret")
    assert info["key_bits"] == 128

    monkeypatch.delenv("MANGLI_AUTH_AES_KEY", raising=False)
    info = describe_configured_aes_key()
    assert info["interpreted_as"] == "unconfigured"
    assert info["env_value_len"] == 0
    assert info["key_bits"] == 0


def test_aes_256_key_roundtrip(monkeypatch):
    """AES-256 密钥下的加解密必须自洽（同 32 字节密钥）。"""
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
        decrypt_mangli_user_header,
        encrypt_mangli_user_header_for_test,
    )

    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "ab" * 32)
    cipher = encrypt_mangli_user_header_for_test('{"userId":"10001"}', key=b"\xab" * 32)
    assert decrypt_mangli_user_header(cipher, key=b"\xab" * 32)["userId"] == "10001"


# ── fail-closed 回归（Q2/Q3/Q4）──────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_aes_key_rejects_gateway_track(monkeypatch):
    """Q2 回归：未配置密钥时不得用公开默认密钥解密网关流量。"""
    monkeypatch.delenv("MANGLI_AUTH_AES_KEY", raising=False)
    sent = []

    async def dummy_app(scope, receive, send):
        raise AssertionError("gateway track must not reach the app")

    async def mock_send(message):
        sent.append(message)

    class FakeAppState:
        lca_auth_expected_token = "secret-token-123"  # noqa: S105
        lca_auth_dev_mode = False

    class FakeApp:
        state = FakeAppState()

    mw = SmartAdaptiveAuthMiddleware(
        dummy_app, auth_service=MangliAuthService(fetch_fn=_allow_all)
    )
    enc = encrypt_mangli_user_header_for_test('{"userId":"10001"}', DEFAULT_AES_KEY)
    scope = {
        "type": "http",
        "path": "/runs",
        "app": FakeApp(),
        "headers": [(b"x-mangli-user", enc.encode()), (b"ticket", b"t")],
    }
    await mw(scope, None, mock_send)
    assert sent[0]["status"] == 503
    assert b"auth_not_configured" in sent[1]["body"]


@pytest.mark.asyncio
async def test_unconfigured_permission_backend_passes_with_empty_roles(monkeypatch):
    """Q3 回归：查询器未接入时权限为空、身份放行，不伪造角色也不 502。"""
    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "fedcba9876543210fedcba9876543210")
    monkeypatch.delenv("MANGLI_PERMISSIONS_ENABLED", raising=False)
    key = bytes.fromhex("fedcba9876543210fedcba9876543210")
    sent = []
    captured = {}

    async def dummy_app(scope, receive, send):
        captured["headers"] = dict(scope.get("headers", []))
        captured["principal"] = get_current_principal()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def mock_send(message):
        sent.append(message)

    class FakeAppState:
        lca_auth_expected_token = "secret-token-123"  # noqa: S105
        lca_auth_dev_mode = False

    class FakeApp:
        state = FakeAppState()

    mw = SmartAdaptiveAuthMiddleware(dummy_app, aes_key=key)
    enc = encrypt_mangli_user_header_for_test('{"userId":"10001"}', key)
    scope = {
        "type": "http",
        "path": "/runs",
        "app": FakeApp(),
        "headers": [(b"x-mangli-user", enc.encode()), (b"ticket", b"any-ticket")],
    }
    await mw(scope, None, mock_send)
    assert sent[0]["status"] == 200
    assert captured["principal"].roles == ()
    assert captured["headers"][b"x-lca-user-id"] == b"10001"


@pytest.mark.asyncio
async def test_permission_query_failure_degrades_to_empty_roles(monkeypatch):
    """Q3 回归：权限接口报错时降级为空权限，不把身份层一起打死。"""
    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "fedcba9876543210fedcba9876543210")
    key = bytes.fromhex("fedcba9876543210fedcba9876543210")
    sent = []
    captured = {}

    async def failing_fetch(ticket: str, user_id: str):
        raise TimeoutError("permission service timeout")

    async def dummy_app(scope, receive, send):
        captured["principal"] = get_current_principal()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def mock_send(message):
        sent.append(message)

    class FakeAppState:
        lca_auth_expected_token = "secret-token-123"  # noqa: S105
        lca_auth_dev_mode = False

    class FakeApp:
        state = FakeAppState()

    mw = SmartAdaptiveAuthMiddleware(
        dummy_app,
        auth_service=MangliAuthService(fetch_fn=failing_fetch),
        aes_key=key,
    )
    enc = encrypt_mangli_user_header_for_test('{"userId":"10001"}', key)
    scope = {
        "type": "http",
        "path": "/runs",
        "app": FakeApp(),
        "headers": [(b"x-mangli-user", enc.encode()), (b"ticket", b"any-ticket")],
    }
    await mw(scope, None, mock_send)
    assert sent[0]["status"] == 200
    assert captured["principal"].roles == ()


@pytest.mark.asyncio
async def test_auth_service_without_fetcher_returns_empty():
    """Q3 回归：无 fetch_fn 时不返回任何权限，也不抛异常阻断请求。"""
    perms, roles = await MangliAuthService().get_permissions("ticket", "user")
    assert perms == []
    assert roles == []


@pytest.mark.asyncio
async def test_missing_auth_config_defaults_to_fail_closed():
    """Q4 回归：未装配 dev_mode/expected_token 时不得放行。"""
    sent = []

    async def dummy_app(scope, receive, send):
        raise AssertionError("unconfigured auth must not pass through")

    async def mock_send(message):
        sent.append(message)

    class EmptyState:
        pass

    class FakeApp:
        state = EmptyState()

    mw = SmartAdaptiveAuthMiddleware(dummy_app, aes_key=DEFAULT_AES_KEY)
    scope = {
        "type": "http",
        "path": "/runs",
        "app": FakeApp(),
        "headers": [
            (b"authorization", b"Bearer lca-local"),
            (b"x-lca-user-id", b"intruder"),
        ],
    }
    await mw(scope, None, mock_send)
    assert sent[0]["status"] == 401
    assert b"auth_not_configured" in sent[1]["body"]
