"""Mangli 企业级 Playground 离线自包含控制台路由插件。

除离线单页外，本插件还承载「经网关」联调通道：浏览器不能跨域直连网关
（网关不提供 CORS），因此由本进程做转发 —— 浏览器始终同源访问
``/playground/proxy/*``，本进程再把请求打到页面指定的网关地址。

安全性完全依赖装配边界：本插件只存在于 dev/test bundle，生产 profile 不装配
（见 ``bundles/mangli-playground-dev.yaml`` 与
``tests/scenario/test_mangli_enterprise_bundle_invariants.py``）。
转发目标与 ticket 由 ``POST /playground/proxy/session`` 一次性绑定，后续请求
只带 session id，凭证不进 URL、不进日志。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.routing import RouteSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.transport.webserver.handlers.cors.cors import cors_headers
from lca.plugins.transport.webserver.route.register import register_routes

_STATIC_DIR = Path(__file__).parent / "static"
_PLAYGROUND_HTML_PATH = _STATIC_DIR / "mangli_playground.html"


def _load_playground_html() -> str:
    if _PLAYGROUND_HTML_PATH.exists():
        return _PLAYGROUND_HTML_PATH.read_text(encoding="utf-8")
    return "<!DOCTYPE html><html><body><h1>Mangli Playground</h1></body></html>"


async def playground_endpoint(request: Request) -> Response:
    """提供纯内网离线自包含的 Playground 验证控制台单页。"""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    html_content = _load_playground_html()
    return HTMLResponse(
        content=html_content,
        status_code=200,
        headers=cors_headers(),
    )


async def playground_encrypt_endpoint(request: Request) -> Response:
    """联调辅助：根据填写的 UserPrincipal 载荷与密钥生成 AES-ECB-PKCS7 密文 Hex。"""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    import json

    from starlette.responses import JSONResponse

    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
        derive_sha1prng_key,
        encrypt_mangli_user_header_for_test,
        get_configured_aes_key,
    )

    try:
        body = await request.json()
        payload = body.get("payload", {})
        key_str = str(body.get("key", "")).strip()
        key_mode = str(body.get("key_mode", "hex")).lower()

        # 空密钥 = "按服务端解密的密钥来加密"，生成即自洽，不会出现
        # "页面生成成功、/runs 却 401 invalid mangli user cipher"。
        key_bytes = get_configured_aes_key()
        if key_str:
            if key_mode == "sha1prng":
                key_bytes = derive_sha1prng_key(key_str.encode("utf-8"))
            elif key_mode == "hex" and len(key_str) == 32:
                key_bytes = bytes.fromhex(key_str)
            else:
                raw = key_str.encode("utf-8")
                key_bytes = raw[:16].ljust(16, b"\0")

        json_str = json.dumps(payload, ensure_ascii=False)
        cipher_hex = encrypt_mangli_user_header_for_test(json_str, key=key_bytes)
        return JSONResponse({"cipher_hex": cipher_hex}, headers=cors_headers())
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400, headers=cors_headers())


def _normalize_cipher_hex(raw: str) -> str:
    """折叠手工粘贴的密文：去空白/换行、去 ``0x``、转小写。

    与服务端解密口径一致（``bytes.fromhex`` 不接受内部空白），页面提交前用
    同一条规则清洗，避免"看着是一串 hex、实际带了换行"的伪故障。
    """
    compact = "".join(str(raw).split())
    if compact[:2].lower() == "0x":
        compact = compact[2:]
    return compact.lower()


def _cipher_hex_problem(normalized: str) -> tuple[str, str] | None:
    """返回 ``(reason, message)``；``None`` 表示形态合法可以尝试解密。"""
    if not normalized:
        return "empty_cipher", "密文为空"
    allowed = set("0123456789abcdef")
    if any(ch not in allowed for ch in normalized):
        return "not_hex", "含非十六进制字符（只允许 0-9 a-f）"
    if len(normalized) % 32 != 0:
        return (
            "bad_block_length",
            f"长度 {len(normalized)} 个 hex 字符，不是 AES 16 字节块（32 hex）的整数倍",
        )
    return None


async def playground_decrypt_endpoint(request: Request) -> Response:
    """联调辅助：用服务端**实际使用**的密钥校验手工密文能否解开。

    手工密文由中间件的 ``MANGLI_AUTH_AES_KEY`` 解密，与页面上填的 AES 密钥
    无关。这个端点让"401 invalid mangli user cipher"从一句不可诊断的话变成
    可分辨的三种原因：形态不合法 / 密钥不匹配 / 不是 ECB-PKCS7。

    只回字段名与字段数，不回明文，避免把身份信息暴露给未鉴权调用方。
    """
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    import os

    from starlette.responses import JSONResponse

    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
        decrypt_mangli_user_header,
        describe_configured_aes_key,
        get_configured_aes_key,
    )

    try:
        body = await request.json()
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "reason": "invalid_body", "message": str(exc)},
            status_code=400,
            headers=cors_headers(),
        )

    raw = body.get("cipher") if isinstance(body, dict) else ""
    if raw is None:
        raw = body.get("cipher_hex") if isinstance(body, dict) else ""
    normalized = _normalize_cipher_hex(raw or "")
    key_origin = "env" if os.environ.get("MANGLI_AUTH_AES_KEY", "").strip() else "default"
    key = get_configured_aes_key()
    key_info = describe_configured_aes_key()

    problem = _cipher_hex_problem(normalized)
    if problem is not None:
        reason, message = problem
        return JSONResponse(
            {
                "ok": False,
                "reason": reason,
                "message": message,
                "key_origin": key_origin,
                "key_bits": key_info["key_bits"],
                "key_info": key_info,
                "cipher_hex_length": len(normalized),
            },
            headers=cors_headers(),
        )

    try:
        data = decrypt_mangli_user_header(normalized, key=key)
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "reason": "decrypt_failed",
                "message": str(exc),
                "key_origin": key_origin,
                "key_bits": key_info["key_bits"],
                "key_info": key_info,
                "cipher_hex_length": len(normalized),
            },
            headers=cors_headers(),
        )

    return JSONResponse(
        {
            "ok": True,
            "key_origin": key_origin,
            "key_bits": key_info["key_bits"],
            "key_info": key_info,
            "cipher_hex_length": len(normalized),
            "field_count": len(data),
            "fields": sorted(str(field) for field in data),
        },
        headers=cors_headers(),
    )


async def playground_diagnose_endpoint(request: Request) -> Response:
    """联调辅助：当 ECB/PKCS7 解不开时，枚举假设定位到底是哪一环不一致。

    区分三种结论：密钥形态解释错（同一份 env 值可被当成 hex / 原文 /
    SHA1PRNG）、分组模式不一致（CBC + IV 固定或前缀）、padding 不一致。
    不返回明文，不回密钥。
    """
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    import os

    from starlette.responses import JSONResponse

    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
        describe_configured_aes_key,
        get_configured_aes_key,
        probe_mangli_cipher_hypotheses,
    )

    try:
        body = await request.json()
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "reason": "invalid_body", "message": str(exc)},
            status_code=400,
            headers=cors_headers(),
        )

    raw = body.get("cipher") if isinstance(body, dict) else ""
    normalized = _normalize_cipher_hex(raw or "")
    problem = _cipher_hex_problem(normalized)
    if problem is not None:
        reason, message = problem
        return JSONResponse(
            {"ok": False, "reason": reason, "message": message},
            headers=cors_headers(),
        )

    key = get_configured_aes_key()
    probe = probe_mangli_cipher_hypotheses(normalized, key)
    return JSONResponse(
        {
            "ok": probe["matched"] is not None,
            "match": probe["matched"],
            "attempted": probe["attempted"],
            "key_sources": probe["key_sources"],
            "notes": probe["notes"],
            "key_origin": "env" if os.environ.get("MANGLI_AUTH_AES_KEY", "").strip() else "default",
            "key_info": describe_configured_aes_key(),
            "configured_key_bits": len(key) * 8,
            "cipher_hex_length": len(normalized),
        },
        headers=cors_headers(),
    )


# ── 经网关联调通道 ───────────────────────────────────────────────────
# 页面不能跨域直连网关（网关无 CORS），所以由本进程转发。转发目标由
# ``POST /playground/proxy/session`` 一次性绑定，后续请求只带 session id。

_PROXY_PREFIX = "/playground/proxy"
PROXY_SESSION_PATH = f"{_PROXY_PREFIX}/session"
PROXY_CATCHALL_PATH = f"{_PROXY_PREFIX}/{{path:path}}"
PROXY_WS_PATH = f"{_PROXY_PREFIX}/v1/runs/{{run_id}}/ws"

PROXY_SESSION_HEADER = "x-playground-session"
PROXY_SESSION_TTL_S = 1800.0

# 只透传业务必要的请求头；cookie / authorization / 身份头一律丢弃，
# 身份只能由被转发的网关决定，页面无法借代理伪造。
_FORWARD_REQUEST_HEADERS = frozenset(
    {
        "content-type",
        "content-length",
        "accept",
        "accept-language",
        "content-disposition",
        "range",
    }
)
_FORWARD_RESPONSE_HEADERS = (
    "content-type",
    "content-disposition",
    "content-length",
    "cache-control",
    "etag",
    "last-modified",
)


@dataclass(frozen=True, slots=True)
class _ProxySession:
    session_id: str
    gateway: str
    ticket: str
    expires_at: float


_PROXY_SESSIONS: dict[str, _ProxySession] = {}
"""进程内代理会话。仅存在于 dev bundle，进程重启即清空。"""


def _prune_proxy_sessions(now: float) -> None:
    for key, session in list(_PROXY_SESSIONS.items()):
        if session.expires_at <= now:
            _PROXY_SESSIONS.pop(key, None)


def normalize_gateway_base(raw: str) -> str:
    """校验页面填写的网关地址，返回去尾斜杠的 base。

    只接受 ``http(s)://host[:port][/prefix]``：代理本身没有鉴权，放开任意
    scheme/相对路径会让它变成通用转发器，拼错时也难诊断。
    """
    value = str(raw or "").strip().rstrip("/")
    if not value:
        raise ValueError("gateway host 不能为空")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"gateway host 必须是 http(s)://host[:port][/prefix] 形式，收到 {raw!r}")
    return value


def create_proxy_session(gateway: str, ticket: str) -> _ProxySession:
    now = time.time()
    _prune_proxy_sessions(now)
    session = _ProxySession(
        session_id=uuid.uuid4().hex,
        gateway=normalize_gateway_base(gateway),
        ticket=str(ticket or "").strip(),
        expires_at=now + PROXY_SESSION_TTL_S,
    )
    _PROXY_SESSIONS[session.session_id] = session
    return session


def get_proxy_session(session_id: str) -> _ProxySession | None:
    if not session_id:
        return None
    now = time.time()
    _prune_proxy_sessions(now)
    session = _PROXY_SESSIONS.get(session_id)
    if session is None or session.expires_at <= now:
        return None
    return session


def reset_proxy_sessions() -> None:
    """测试钩子：清空进程内代理会话。"""
    _PROXY_SESSIONS.clear()


def _proxy_target(session: _ProxySession, request: Request) -> str:
    tail = str(request.path_params.get("path", "") or "").lstrip("/")
    url = f"{session.gateway}/{tail}"
    query = request.url.query
    return f"{url}?{query}" if query else url


def _ws_upstream_url(session: _ProxySession, tail: str) -> str:
    parts = urlsplit(session.gateway)
    scheme = "wss" if parts.scheme == "https" else "ws"
    base = parts._replace(scheme=scheme).geturl().rstrip("/")
    return f"{base}/{tail.lstrip('/')}"


async def playground_proxy_session_endpoint(request: Request) -> Response:
    """绑定一次联调：网关地址 + ticket，返回后续请求要带的 session id。"""
    from starlette.responses import JSONResponse

    try:
        body = await request.json()
    except Exception as exc:
        return JSONResponse(
            {"error": {"code": "invalid_body", "message": str(exc)}},
            status_code=400,
            headers=cors_headers(),
        )
    if not isinstance(body, dict):
        return JSONResponse(
            {"error": {"code": "invalid_body", "message": "body 必须是 JSON 对象"}},
            status_code=400,
            headers=cors_headers(),
        )
    try:
        session = create_proxy_session(body.get("gateway", ""), body.get("ticket", ""))
    except ValueError as exc:
        return JSONResponse(
            {"error": {"code": "invalid_gateway", "message": str(exc)}},
            status_code=400,
            headers=cors_headers(),
        )
    return JSONResponse(
        {
            "session_id": session.session_id,
            "gateway": session.gateway,
            "ticket_present": bool(session.ticket),
            "expires_in": int(PROXY_SESSION_TTL_S),
        },
        headers=cors_headers(),
    )


async def playground_proxy_endpoint(request: Request) -> Response:
    """把浏览器请求原样转发到网关，并把响应流回传。

    只搬运 body 与白名单头；状态码 / content-type / content-disposition 原样
    返回，页面才能像直连一样判断 4xx 与下载文件名。
    """
    import httpx
    from starlette.background import BackgroundTask
    from starlette.responses import JSONResponse, StreamingResponse

    session = get_proxy_session(request.headers.get(PROXY_SESSION_HEADER, ""))
    if session is None:
        return JSONResponse(
            {
                "error": {
                    "code": "proxy_session_missing",
                    "message": "代理会话不存在或已过期，请在页面上重新点「连接测试」",
                }
            },
            status_code=403,
            headers=cors_headers(),
        )

    target = _proxy_target(session, request)
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() in _FORWARD_REQUEST_HEADERS
    }
    if session.ticket:
        headers["ticket"] = session.ticket

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=300.0, pool=10.0),
        follow_redirects=False,
    )
    try:
        upstream_request = client.build_request(
            request.method,
            target,
            headers=headers,
            content=request.stream(),
        )
        upstream_response = await client.send(upstream_request, stream=True)
    except Exception as exc:
        await client.aclose()
        return JSONResponse(
            {
                "error": {
                    "code": "proxy_upstream_error",
                    "message": f"网关请求失败: {exc}",
                    "target": f"{session.gateway}/…",
                }
            },
            status_code=502,
            headers=cors_headers(),
        )

    async def _release() -> None:
        with contextlib.suppress(Exception):
            await upstream_response.aclose()
        with contextlib.suppress(Exception):
            await client.aclose()

    out_headers = {
        name: upstream_response.headers[name]
        for name in _FORWARD_RESPONSE_HEADERS
        if name in upstream_response.headers
    }
    return StreamingResponse(
        upstream_response.aiter_raw(),
        status_code=upstream_response.status_code,
        headers=out_headers,
        background=BackgroundTask(_release),
    )


async def _pump_proxy_ws(websocket: Any, upstream: Any) -> None:
    """双向搬运 WS 帧；任一方向结束即收敛，关闭码随后由调用方统一处理。"""

    async def browser_to_upstream() -> None:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            text = message.get("text")
            if text is not None:
                await upstream.send(text)
                continue
            data = message.get("bytes")
            if data is not None:
                await upstream.send(data)

    async def upstream_to_browser() -> None:
        async for message in upstream:
            if isinstance(message, bytes):
                await websocket.send_bytes(message)
            else:
                await websocket.send_text(message)

    tasks = [
        asyncio.create_task(browser_to_upstream()),
        asyncio.create_task(upstream_to_browser()),
    ]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(BaseException):
                await task


async def playground_proxy_ws(websocket: Any) -> None:
    """WS 代理：浏览器同源连本进程，本进程带 ticket 连网关。

    session 走 query 参数而非请求头 —— 浏览器无法给 ``new WebSocket`` 加自定义
    头；session id 是随机值且 30 分钟过期，ticket 本身不进 URL。
    """
    import websockets

    run_id = str(websocket.path_params.get("run_id", "") or "")
    session = get_proxy_session(websocket.query_params.get(PROXY_SESSION_HEADER, ""))
    await websocket.accept()

    if session is None:
        await websocket.send_json(
            {
                "type": "auth_failed",
                "reason": "playground proxy session missing or expired",
            }
        )
        await websocket.close()
        return

    upstream_url = _ws_upstream_url(session, f"/v1/runs/{run_id}/ws")
    try:
        upstream = await websockets.connect(
            upstream_url,
            additional_headers={"ticket": session.ticket} if session.ticket else None,
            open_timeout=15,
            close_timeout=5,
            ping_interval=None,
            max_size=None,
        )
    except Exception as exc:
        await websocket.send_json(
            {"type": "auth_failed", "reason": f"gateway connect failed: {exc}"}
        )
        await websocket.close()
        return

    try:
        await _pump_proxy_ws(websocket, upstream)
    finally:
        with contextlib.suppress(Exception):
            await upstream.close()
        with contextlib.suppress(Exception):
            await websocket.close()


async def playground_whoami_endpoint(request: Request) -> Response:
    """回显本进程当前认定的身份。

    必须放在中间件覆盖的路径上（不能挂 ``/playground/*``，那里免鉴权、不会解
    密），这样经网关调用时看到的就是网关注入的结果，直连时是自己的结果。
    只回 userId 与字段名，不回姓名手机号等明文。
    """
    from starlette.responses import JSONResponse

    principal = getattr(request.state, "principal", None)
    if principal is None:
        return JSONResponse(
            {"authenticated": False, "issuer": "", "userId": "", "fields": []},
            headers=cors_headers(),
        )
    fields = [
        name
        for name in (
            "user_id",
            "name",
            "job_number",
            "mobile",
            "email",
            "job_name",
            "department",
            "clock_in_type",
        )
        if getattr(principal, name, None)
    ]
    return JSONResponse(
        {
            "authenticated": True,
            "issuer": str(getattr(principal, "issuer", "") or ""),
            "userId": str(
                getattr(principal, "user_id", "") or getattr(principal, "subject", "") or ""
            ),
            "ticket_present": bool(getattr(principal, "ticket", "")),
            "fields": fields,
        },
        headers=cors_headers(),
    )


PLAYGROUND_ROUTE_SPECS = (
    RouteSpec(
        "/playground",
        playground_endpoint,
        ("GET", "HEAD", "OPTIONS"),
    ),
    # session 必须排在 catch-all 之前，否则会被当成普通转发路径吃掉。
    RouteSpec(PROXY_SESSION_PATH, playground_proxy_session_endpoint, ("POST", "OPTIONS")),
    RouteSpec(
        PROXY_CATCHALL_PATH,
        playground_proxy_endpoint,
        ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"),
    ),
    RouteSpec("/whoami", playground_whoami_endpoint, ("GET", "OPTIONS")),
    RouteSpec(
        "/playground/encrypt",
        playground_encrypt_endpoint,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/playground/decrypt",
        playground_decrypt_endpoint,
        ("POST", "OPTIONS"),
    ),
    RouteSpec(
        "/playground/diagnose",
        playground_diagnose_endpoint,
        ("POST", "OPTIONS"),
    ),
)


@plugin(
    id="mangli-enterprise-playground-route",
    provides=(),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="network",
    description="Mangli 离线自包含 Playground 控制台路由插件（含经网关联调代理）",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("mangli-enterprise-playground-route.served",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("mangli_playground_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """挂载 /playground 验证单页路由与经网关联调通道。"""
    registry = ctx.require("route_registry")
    register_routes(
        registry,
        ctx,
        PLAYGROUND_ROUTE_SPECS,
        plugin_id="mangli-enterprise-playground-route",
    )

    from starlette.routing import WebSocketRoute

    ws_dispose = registry.register_websocket(WebSocketRoute(PROXY_WS_PATH, playground_proxy_ws))
    inner: Any = ctx._runtime()  # type: ignore[attr-defined]
    inner.effect(ws_dispose, label=f"ws:{PROXY_WS_PATH}")


__all__ = [
    "PLAYGROUND_ROUTE_SPECS",
    "PROXY_SESSION_HEADER",
    "PROXY_SESSION_PATH",
    "PROXY_WS_PATH",
    "create_proxy_session",
    "get_proxy_session",
    "normalize_gateway_base",
    "playground_decrypt_endpoint",
    "playground_diagnose_endpoint",
    "playground_encrypt_endpoint",
    "playground_endpoint",
    "playground_proxy_endpoint",
    "playground_proxy_session_endpoint",
    "playground_proxy_ws",
    "playground_whoami_endpoint",
    "reset_proxy_sessions",
    "setup",
]
