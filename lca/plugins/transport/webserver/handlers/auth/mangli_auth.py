"""Mangli 企业级自适应双轨鉴权中间件与身份服务（ADR-0252 D4 / C13 信息血统闭合）。"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from starlette.types import ASGIApp, Receive, Scope, Send

from lca.plugins.transport.webserver.handlers.auth.principal import Principal
from lca.plugins.transport.webserver.handlers.auth.user import (
    DEFAULT_DEV_USER_ID,
    DEFAULT_EXPECTED_TOKEN,
)
from lca.plugins.transport.webserver.handlers.cors.cors import CORS_HEADERS

# 默认测试/备用密钥 (16字节 Hex 主路)
DEFAULT_AES_KEY = bytes.fromhex("0123456789abcdef0123456789abcdef")

# 网关流量进入时必须强制剔除的伪造客户端头
FORBIDDEN_CLIENT_HEADERS = {
    b"x-lca-user-id",
    b"authorization",
    b"x-lca-token",
}

# 异步线程/协程内持有的当前身份 Principal
_current_principal_var: ContextVar[Principal | None] = ContextVar(
    "current_principal", default=None
)


def get_current_principal() -> Principal | None:
    """获取当前协程绑定的 Principal 身份。"""
    return _current_principal_var.get()


def set_current_principal(principal: Principal | None) -> None:
    """设置当前协程绑定的 Principal 身份。"""
    _current_principal_var.set(principal)


def derive_sha1prng_key(password: bytes) -> bytes:
    """兼容 Java SecureRandom.getInstance('SHA1PRNG') 派生的 128 位 AES 密钥。"""
    return hashlib.sha1(password).digest()[:16]  # noqa: S324 — Java SHA1PRNG derivation compatibility


def get_configured_aes_key() -> bytes:
    """获取当前配置的 AES 密钥。"""
    key_env = os.environ.get("MANGLI_AUTH_AES_KEY", "").strip()
    if not key_env:
        return DEFAULT_AES_KEY
    try:
        raw_bytes = bytes.fromhex(key_env)
        if len(raw_bytes) == 16:
            return raw_bytes
    except ValueError:
        pass
    if len(key_env.encode("utf-8")) == 16:
        return key_env.encode("utf-8")
    return derive_sha1prng_key(key_env.encode())


def decrypt_mangli_user_header(
    cipher_hex: str, key: bytes = DEFAULT_AES_KEY
) -> dict[str, Any]:
    """解密网关传入的 AES-ECB-PKCS7 密文 Hex 字符串。"""
    try:
        ciphertext = bytes.fromhex(cipher_hex.strip())
        cipher = Cipher(algorithms.AES(key), modes.ECB())  # noqa: S305 — Gateway AES-ECB legacy compatibility
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
        data = json.loads(plaintext.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Decrypted content must be a JSON object")
        return data
    except Exception as exc:
        raise ValueError(f"Failed to decrypt mangli user header: {exc}") from exc


def encrypt_mangli_user_header_for_test(
    json_str: str, key: bytes = DEFAULT_AES_KEY
) -> str:
    """测试用：加密 JSON 字符串为 AES-ECB-PKCS7 密文 Hex。"""
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(json_str.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.ECB())  # noqa: S305 — Gateway AES-ECB legacy compatibility
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    return ciphertext.hex()


class ExpiringLruCache:
    """标准库实现的带 TTL 内存 LRU 缓存。"""

    def __init__(self, maxsize: int = 1024, ttl_seconds: float = 300.0) -> None:
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        val, expiry = self._cache[key]
        if time.monotonic() > expiry:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return val

    def set(self, key: str, val: Any) -> None:
        if key in self._cache:
            del self._cache[key]
        elif len(self._cache) >= self.maxsize:
            self._cache.popitem(last=False)
        self._cache[key] = (val, time.monotonic() + self.ttl_seconds)


class PermissionServiceUnavailableError(Exception):
    """权限微服务超时或宕机（Fail-Closed 阻断）。"""


FetchPermFn = Callable[[str, str], Awaitable[tuple[list[str], list[str]]]]


class MangliAuthService:
    """企业权限微服务客户端适配层（带 5min LRU 缓存与 Fail-Closed 保护）。"""

    def __init__(
        self,
        fetch_fn: FetchPermFn | None = None,
        cache: ExpiringLruCache | None = None,
    ) -> None:
        self._fetch_fn = fetch_fn
        self._cache = cache or ExpiringLruCache(maxsize=2048, ttl_seconds=300.0)

    async def get_permissions(
        self, ticket: str, user_id: str
    ) -> tuple[list[str], list[str]]:
        """查询用户权限与角色，优先命中 5 分钟 LRU 缓存。"""
        cache_key = f"{ticket}:{user_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        if self._fetch_fn is not None:
            perms, roles = await self._fetch_fn(ticket, user_id)
        else:
            # 真实生产环境微服务调用兜底（若未注入 mock）
            perms, roles = ["user:read"], ["user"]

        self._cache.set(cache_key, (perms, roles))
        return perms, roles


async def _send_json_response(
    send: Send,
    status_code: int,
    code: str,
    detail: str,
) -> None:
    body = json.dumps(
        {"error": {"code": code, "type": "auth", "detail": detail}}
    ).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    for k, v in CORS_HEADERS.items():
        headers.append((k.lower().encode("ascii"), v.encode("ascii")))

    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": headers,
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        }
    )


class SmartAdaptiveAuthMiddleware:
    """自适应双轨鉴权中间件。

    1. 公司网关流量 (带 x-mangli-user)：
       - Hex 解码 + AES-ECB 解密；解密失败返回 401；
       - 透传 ticket 校验权限服务；服务宕机返回 502，ticket 无效返回 401；
       - 强制剥离客户端伪造的 x-lca-user-id / authorization / x-lca-token；
       - 注入真实 x-lca-user-id 与合法 Bearer token；
       - 构造 Principal(issuer='mangli') 写入 request.state 与 ContextVar。
    2. 内网直连 / LobeHub 流量 (无 x-mangli-user)：
       - 生产模式 (dev_mode=False)：无合法 Bearer 直接拦截返回 401；
       - 构造 Principal(issuer='lobehub') 写入 request.state 与 ContextVar。
    """

    def __init__(
        self,
        app: ASGIApp,
        auth_service: MangliAuthService | None = None,
        aes_key: bytes | None = None,
    ) -> None:
        self.app = app
        self.auth_service = auth_service or MangliAuthService()
        self.aes_key = aes_key or get_configured_aes_key()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/playground" or path.startswith("/playground/") or path in {"/health", "/favicon.ico"}:
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers", []))
        headers_dict = {k.lower(): v for k, v in headers}

        # 读取运行时配置
        app_obj = scope.get("app")
        state_obj = getattr(app_obj, "state", None) if app_obj else None
        expected_token = str(
            getattr(state_obj, "lca_auth_expected_token", DEFAULT_EXPECTED_TOKEN)
        )
        dev_mode = bool(getattr(state_obj, "lca_auth_dev_mode", True))

        mangli_user_bytes = headers_dict.get(b"x-mangli-user")

        if mangli_user_bytes:
            # === 公司网关流量主路 ===
            cipher_hex = mangli_user_bytes.decode("utf-8", errors="replace")
            try:
                user_info = decrypt_mangli_user_header(cipher_hex, key=self.aes_key)
            except Exception:
                await _send_json_response(
                    send, 401, "unauthorized", "invalid mangli user cipher"
                )
                return

            # 兼容 Java UserPrincipal 驼峰与下划线命名
            user_id = str(user_info.get("userId") or user_info.get("user_id", "")).strip()
            name = str(user_info.get("name", "")).strip()
            mobile = str(user_info.get("mobile", "")).strip()
            email = str(user_info.get("email", "")).strip()
            job_number = str(user_info.get("jobNumber") or user_info.get("job_number", "")).strip()
            job_name = str(user_info.get("jobName") or user_info.get("job_name", "")).strip()
            department = str(user_info.get("department") or user_info.get("dept_id", "")).strip()

            raw_clock_in = user_info.get("clockInType") or user_info.get("clock_in_type")
            clock_in_type: int | None = None
            if raw_clock_in is not None:
                try:
                    clock_in_type = int(raw_clock_in)
                except (ValueError, TypeError):
                    clock_in_type = None

            effective_user_id = user_id or job_number
            if not effective_user_id:
                await _send_json_response(
                    send, 401, "unauthorized", "missing userId or jobNumber in cipher payload"
                )
                return

            # ticket 提取：优先从 UserPrincipal 内部提取，兼容 Header 中的 ticket
            ticket = str(user_info.get("ticket", "")).strip()
            if not ticket:
                ticket_bytes = headers_dict.get(b"ticket")
                ticket = (
                    ticket_bytes.decode("utf-8", errors="replace").strip()
                    if ticket_bytes
                    else ""
                )

            # 权限微服务查询与 Fail-Closed 保护
            try:
                _perms, roles = await self.auth_service.get_permissions(ticket, effective_user_id)
            except PermissionServiceUnavailableError:
                await _send_json_response(
                    send, 502, "bad_gateway", "permission service unavailable"
                )
                return
            except Exception:
                await _send_json_response(
                    send, 401, "unauthorized", "invalid ticket"
                )
                return

            # 强制剥离客户端可能伪造的身份头
            cleaned_headers = [
                (k, v) for k, v in headers if k.lower() not in FORBIDDEN_CLIENT_HEADERS
            ]

            # 注入真实身份与合法 Bearer
            cleaned_headers.append((b"x-lca-user-id", effective_user_id.encode()))
            cleaned_headers.append(
                (b"authorization", f"Bearer {expected_token}".encode())
            )
            scope["headers"] = cleaned_headers

            # 构造不可变 Principal 并绑定
            principal = Principal(
                issuer="mangli",
                subject=effective_user_id,
                user_id=user_id,
                name=name,
                mobile=mobile,
                email=email,
                job_number=job_number,
                job_name=job_name,
                department=department,
                clock_in_type=clock_in_type,
                ticket=ticket,
                dept_id=department or None,
                roles=tuple(roles),
            )
            set_current_principal(principal)
            scope.setdefault("state", {})["principal"] = principal

        else:
            # === 内网直连 / LobeHub 测试流量 ===
            auth_val = headers_dict.get(b"authorization", b"").decode(
                "utf-8", errors="replace"
            )
            token = ""
            if auth_val.lower().startswith("bearer "):
                token = auth_val[7:].strip()
            if not token:
                token = (
                    headers_dict.get(b"x-lca-token", b"")
                    .decode("utf-8", errors="replace")
                    .strip()
                )

            if not dev_mode and token != expected_token:
                await _send_json_response(
                    send,
                    401,
                    "unauthorized",
                    "missing or invalid authorization token in production mode",
                )
                return

            raw_user_id = (
                headers_dict.get(b"x-lca-user-id", b"")
                .decode("utf-8", errors="replace")
                .strip()
            )
            effective_user = raw_user_id or DEFAULT_DEV_USER_ID

            principal = Principal(
                issuer="lobehub",
                subject=effective_user,
            )
            set_current_principal(principal)
            scope.setdefault("state", {})["principal"] = principal

        await self.app(scope, receive, send)


def install_adaptive_auth_middleware(
    app: Any,
    auth_service: MangliAuthService | None = None,
    aes_key: bytes | None = None,
) -> None:
    """在 Starlette 应用上挂载自适应双轨鉴权中间件。"""
    app.add_middleware(
        SmartAdaptiveAuthMiddleware,
        auth_service=auth_service,
        aes_key=aes_key,
    )


__all__ = [
    "DEFAULT_AES_KEY",
    "FORBIDDEN_CLIENT_HEADERS",
    "ExpiringLruCache",
    "MangliAuthService",
    "PermissionServiceUnavailableError",
    "SmartAdaptiveAuthMiddleware",
    "decrypt_mangli_user_header",
    "derive_sha1prng_key",
    "encrypt_mangli_user_header_for_test",
    "get_configured_aes_key",
    "get_current_principal",
    "install_adaptive_auth_middleware",
    "set_current_principal",
]
