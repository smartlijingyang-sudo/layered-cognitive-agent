"""Tests for Mangli enterprise playground offline self-contained web console (INV-06)."""

import json

from starlette.applications import Starlette
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.routes_mangli_playground import (
    PLAYGROUND_ROUTE_SPECS,
)


def test_playground_offline_render():
    app = Starlette()
    for spec in PLAYGROUND_ROUTE_SPECS:
        app.add_route(spec.path, spec.handler, methods=list(spec.methods))

    client = TestClient(app)
    res = client.get("/playground")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "cdn.tailwindcss.com" not in res.text
    assert "unpkg.com" not in res.text
    assert "<style>" in res.text
    # 验证界面包含 WebSocket 首帧认证逻辑
    assert 'type: "auth"' in res.text or '"type": "auth"' in res.text


def test_playground_streams_gateway_agent_events():
    """Playground 必须用网关真实协议：auth 后发 resume、渲染 agent_event 信封。

    回归：早期版本按 chunk/tool_called/file_generated/done 解析，而网关只会
    发送 ``{"type": "agent_event", "event": {...}}``，导致所有事件被静默丢弃。
    """
    app = Starlette()
    for spec in PLAYGROUND_ROUTE_SPECS:
        app.add_route(spec.path, spec.handler, methods=list(spec.methods))

    res = TestClient(app).get("/playground")
    text = res.text
    assert res.status_code == 200
    # auth 之后必须补 resume 帧，否则服务端阻塞在第二次 recv（等到 30s 心跳）
    assert "type: 'resume'" in text
    assert "lastEventId" in text
    # 必须解析 agent_event 信封与其真实子类型
    assert "agent_event" in text
    assert "renderAgentEvent" in text
    assert "stream_chunk" in text
    assert "agent_runtime_end" in text
    # 旧的伪协议解析分支必须彻底删除，不留死代码
    assert "tool_called" not in text
    assert "file_generated" not in text


def test_playground_supports_file_upload():
    """Playground 必须能上传附件并随 run 提交。

    回归：早期版本只有一个「产物下载」列表，页面上没有任何上传入口，用户
    无法把本地文件交给 agent（后端 ``POST /files`` 已就绪却无消费者）。
    """
    from lca.plugins.transport.webserver.handlers.files.upload import _UPLOAD_FIELD
    from lca.plugins.transport.webserver.routes_company_files import PLUGIN_ID

    app = Starlette()
    for spec in PLAYGROUND_ROUTE_SPECS:
        app.add_route(spec.path, spec.handler, methods=list(spec.methods))

    text = TestClient(app).get("/playground").text
    # 上传入口：文件选择 + 拖拽区，二者共用同一个上传函数
    assert 'type="file"' in text
    assert 'id="fileInput"' in text
    assert 'ondrop="onDrop(event)"' in text
    assert "uploadFiles(" in text
    # 字段名必须与后端 multipart 契约一致（重复同名字段承载多文件）
    assert "FormData" in text
    assert f"'{_UPLOAD_FIELD}'" in text
    assert "fetch(apiUrl('/files')" in text
    # 上传与 run 共用同一份双轨鉴权头，不允许第二套
    assert "buildAuthHeaders" in text
    # 附件以 /files/{id} 相对 URL 声明，命中后端本地分支
    assert "userMessage.files" in text
    assert "fileservice_unconfigured" in text
    # 上传接缝仍然是路由插件提供的那个入口，未新开平行通道
    assert PLUGIN_ID == "lca-gateway-routes-company-files"


def _playground_text() -> str:
    app = Starlette()
    for spec in PLAYGROUND_ROUTE_SPECS:
        app.add_route(spec.path, spec.handler, methods=list(spec.methods))
    return TestClient(app).get("/playground").text


def test_playground_supports_hitl_approval():
    """Playground 必须能在 human_approval 暂停后恢复 run。

    回归：服务端在暂停时按协议发 ``step_start{phase: human_approval}`` +
    ``agent_runtime_end{reason: waiting_for_human}`` 然后关闭事件流；早期页面
    把 ``agent_runtime_end`` 当终点，没有审批面板、没有 answer 调用、没有重连，
    所以前端永远停在 ``reason=waiting_for_human``。
    """
    text = _playground_text()
    # 暂停信号必须被识别并渲染成可操作面板
    assert "human_approval" in text
    assert "waiting_for_human" in text
    assert 'id="approvalPanel"' in text
    assert "renderApprovalPanel" in text
    assert "pendingToolsCalling" in text
    # 审批回传必须走既有 durable 契约，不新开旁路
    assert "/answer" in text
    assert "approval_id" in text
    assert "idempotency_key" in text
    assert "rejection_reason" in text
    # 暂停后事件流已关闭：必须换 ws-token 重建连接，并用 lastEventId 续传
    assert "/ws-token" in text
    assert "lastEventId" in text
    assert "fromScratch" in text


def test_playground_supports_cancel_run():
    """页面必须能手停一个不受控输出的 run。

    回归：早期页面开跑后没有任何停止入口，模型持续输出时用户只能整页刷新，
    服务端 run 仍在跑并继续消耗额度。
    """
    text = _playground_text()
    assert 'id="stopBtn"' in text
    assert "cancelRun" in text
    # 停止必须走 HTTP cancel：暂停态下 WS 已断开，interrupt 帧发不出去。
    assert "/cancel" in text
    assert "setRunActive" in text


def test_playground_supports_history_and_run_replay():
    """Playground 必须支持多轮上下文与既有 run 回放（验证历史任务的入口）。"""
    text = _playground_text()
    # 多轮：本页完成的轮次作为 messages 前缀提交
    assert "transcript" in text
    assert "transcript.concat" in text
    assert "role: 'assistant'" in text
    # 回放：粘贴 run_id 从头重播；流失效时回退 GET /runs/{id} 摘要
    assert 'id="attachRunId"' in text
    assert "attachExistingRun" in text
    assert "renderRunSummary" in text
    assert "/runs/${runId}`" in text


def test_playground_encrypt_api():
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import decrypt_mangli_user_header

    app = Starlette()
    for spec in PLAYGROUND_ROUTE_SPECS:
        app.add_route(spec.path, spec.handler, methods=list(spec.methods))

    client = TestClient(app)
    res = client.post(
        "/playground/encrypt",
        json={
            "payload": {
                "userId": "10001",
                "name": "张三",
                "jobNumber": "E10001",
                "mobile": "13800138000",
                "email": "zhangsan@company.com",
                "jobName": "架构师",
                "department": "技术部",
                "clockInType": 1,
                "ticket": "TKT-MANGLI-001",
            },
            "key": "0123456789abcdef0123456789abcdef",
            "key_mode": "hex",
        },
    )
    assert res.status_code == 200
    cipher_hex = res.json()["cipher_hex"]
    assert cipher_hex

    # 验证生成的密文可被后端解密且字段 100% 对齐
    decrypted = decrypt_mangli_user_header(
        cipher_hex, bytes.fromhex("0123456789abcdef0123456789abcdef")
    )
    assert decrypted["userId"] == "10001"
    assert decrypted["name"] == "张三"
    assert decrypted["jobNumber"] == "E10001"
    assert decrypted["ticket"] == "TKT-MANGLI-001"


def _client() -> TestClient:
    app = Starlette()
    for spec in PLAYGROUND_ROUTE_SPECS:
        app.add_route(spec.path, spec.handler, methods=list(spec.methods))
    return TestClient(app)


def test_playground_manual_cipher_has_preflight_check():
    """手工密文必须能先自检，而不是只能靠 /runs 的 401 猜。

    回归：中间件用 ``MANGLI_AUTH_AES_KEY`` 解密，页面上的密钥框只影响
    「生成密文」；早期页面把 ``401 invalid mangli user cipher`` 原样丢给用户，
    无法区分「形态不合法」与「密钥不匹配」。
    """
    text = _playground_text()
    assert 'id="cipherNotice"' in text
    assert "verifyCipher" in text
    assert "/playground/decrypt" in text
    assert "normalizeCipherHex" in text
    assert "authHint" in text
    # 密钥模式必须能选「服务端已配置密钥」，避免生成/解密两套密钥
    assert 'value="server"' in text
    assert "MANGLI_AUTH_AES_KEY" in text
    # 该模式下页面密钥框不参与计算，必须被禁用而不是留着误导
    assert "toggleKeyMode" in text
    # 解不开时必须能进一步定位是密钥错还是模式错
    assert "/playground/diagnose" in text
    assert "diagnoseCipher" in text


def test_playground_decrypt_api(monkeypatch):
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
        encrypt_mangli_user_header_for_test,
    )

    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "fedcba9876543210fedcba9876543210")
    key = bytes.fromhex("fedcba9876543210fedcba9876543210")
    cipher = encrypt_mangli_user_header_for_test(
        json.dumps({"userId": "10001", "name": "张三"}, ensure_ascii=False), key=key
    )
    client = _client()

    ok = client.post("/playground/decrypt", json={"cipher": cipher})
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert body["key_origin"] == "env"
    assert "userId" in body["fields"]

    # 粘贴常见污染：0x 前缀 / 大写 / 内部换行 —— 与页面同一条清洗规则
    messy = "0x" + cipher.upper()
    wrapped = f"{messy[:16]}\n{messy[16:]}"
    assert client.post("/playground/decrypt", json={"cipher": wrapped}).json()["ok"] is True

    # 用默认密钥加密的密文：形态合法但解不开 → 密钥不匹配
    other = encrypt_mangli_user_header_for_test(
        json.dumps({"userId": "x"}), key=bytes.fromhex("0123456789abcdef0123456789abcdef")
    )
    mismatch = client.post("/playground/decrypt", json={"cipher": other}).json()
    assert mismatch["ok"] is False
    assert mismatch["reason"] == "decrypt_failed"

    assert client.post("/playground/decrypt", json={"cipher": "zz"}).json()["reason"] == "not_hex"
    assert (
        client.post("/playground/decrypt", json={"cipher": "abcd"}).json()["reason"]
        == "bad_block_length"
    )
    assert (
        client.post("/playground/decrypt", json={"cipher": "   "}).json()["reason"]
        == "empty_cipher"
    )


def test_playground_encrypt_defaults_to_server_key(monkeypatch):
    """页面留空密钥 = 用服务端解密的那把密钥加密，生成即可用。"""
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import decrypt_mangli_user_header

    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "fedcba9876543210fedcba9876543210")
    res = _client().post(
        "/playground/encrypt",
        json={"payload": {"userId": "10001"}, "key": "", "key_mode": "server"},
    )
    assert res.status_code == 200
    decrypted = decrypt_mangli_user_header(
        res.json()["cipher_hex"], key=bytes.fromhex("fedcba9876543210fedcba9876543210")
    )
    assert decrypted["userId"] == "10001"


def _encrypt_cbc_prefix_iv(plaintext: str, key: bytes, iv: bytes) -> str:
    from cryptography.hazmat.primitives import padding as sym_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode()) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return (iv + ciphertext).hex()


def test_playground_diagnose_identifies_ecb_match(monkeypatch):
    """ECB/PKCS7 密文：诊断应报告与服务端实现一致。"""
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
        encrypt_mangli_user_header_for_test,
    )

    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "fedcba9876543210fedcba9876543210")
    key = bytes.fromhex("fedcba9876543210fedcba9876543210")
    cipher = encrypt_mangli_user_header_for_test(json.dumps({"userId": "10001"}), key=key)
    body = _client().post("/playground/diagnose", json={"cipher": cipher}).json()
    assert body["ok"] is True
    assert body["match"]["mode"] == "ECB"
    assert body["match"]["padding"] == "pkcs7"
    assert body["match"]["key_source"] == "configured"
    assert body["configured_key_bits"] == 128


def test_playground_diagnose_identifies_cbc_prefix_iv(monkeypatch):
    """CBC + IV 前缀：诊断必须指出模式不一致，而不是笼统说"密钥不对"。

    这正是"密钥明明一样却解不开"的典型形态：AES 对称但分组模式不同。
    """
    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "fedcba9876543210fedcba9876543210")
    key = bytes.fromhex("fedcba9876543210fedcba9876543210")
    iv = bytes.fromhex("00112233445566778899aabbccddeeff")
    cipher = _encrypt_cbc_prefix_iv(json.dumps({"userId": "10001"}), key, iv)
    body = _client().post("/playground/diagnose", json={"cipher": cipher}).json()
    assert body["ok"] is True
    assert body["match"]["mode"] == "CBC"
    assert body["match"]["iv"] == "prefix16"


def test_playground_diagnose_reports_key_mismatch(monkeypatch):
    """密钥完全不同：所有假设都失败，结论落在密钥而非格式。"""
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
        encrypt_mangli_user_header_for_test,
    )

    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "fedcba9876543210fedcba9876543210")
    cipher = encrypt_mangli_user_header_for_test(
        json.dumps({"userId": "10001"}), key=bytes.fromhex("aabbccddeeff00112233445566778899")
    )
    body = _client().post("/playground/diagnose", json={"cipher": cipher}).json()
    assert body["ok"] is False
    assert body["match"] is None
    assert body["attempted"] > 0
    assert any("全部失败" in note for note in body["notes"])
    # 必须把「试过哪些密钥形态」告诉用户，否则"全部失败"仍然不可诊断
    assert "sha1prng" in body["key_sources"] or "env_text" in body["key_sources"]


def test_playground_diagnose_identifies_iv_equals_key(monkeypatch):
    """CBC + IV=密钥本身：企业代码最常见的复制粘贴写法，也必须能识别。"""
    from cryptography.hazmat.primitives import padding as sym_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "fedcba9876543210fedcba9876543210")
    key = bytes.fromhex("fedcba9876543210fedcba9876543210")
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(json.dumps({"userId": "10001"}).encode()) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    cipher = (encryptor.update(padded) + encryptor.finalize()).hex()

    body = _client().post("/playground/diagnose", json={"cipher": cipher}).json()
    assert body["ok"] is True
    assert body["match"]["mode"] == "CBC"
    assert body["match"]["iv"] == "key16"


def test_playground_diagnose_reports_server_interpretation(monkeypatch):
    """配置值长度不合法时，诊断必须把"服务端读到的字节数"摆出来。"""
    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
        encrypt_mangli_user_header_for_test,
    )

    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", "mangli-secret")  # 13 字节，非 16/24/32
    cipher = encrypt_mangli_user_header_for_test(
        json.dumps({"userId": "10001"}), key=bytes.fromhex("aabbccddeeff00112233445566778899")
    )
    body = _client().post("/playground/diagnose", json={"cipher": cipher}).json()
    assert body["ok"] is False
    assert body["key_info"]["interpreted_as"] == "sha1prng"
    assert body["key_info"]["env_value_len"] == len("mangli-secret")


def test_playground_diagnose_identifies_md5_derivation(monkeypatch):
    """网关用 MD5(密码) 派生、服务端用 SHA1PRNG：诊断必须点出派生规则不一致。"""
    import hashlib

    from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
        encrypt_mangli_user_header_for_test,
    )

    gateway_secret = "mangli@2026"  # noqa: S105 — 测试用假密钥，不是真实凭据
    monkeypatch.setenv("MANGLI_AUTH_AES_KEY", gateway_secret)
    key = hashlib.md5(gateway_secret.encode()).digest()[:16]  # noqa: S324 — 模拟网关派生
    cipher = encrypt_mangli_user_header_for_test(json.dumps({"userId": "10001"}), key=key)
    body = _client().post("/playground/diagnose", json={"cipher": cipher}).json()
    assert body["ok"] is True
    assert body["match"]["key_source"] == "md5_16"
    assert body["match"]["mode"] == "ECB"
    assert any("派生规则" in note for note in body["notes"])


# ── 经网关通道 ───────────────────────────────────────────────────────
# 浏览器不能跨域直连网关（网关无 CORS），所以页面只访问本服务，由本服务
# 带 ticket 转发。下面锁住这条通道的三件事：会话绑定、头过滤、身份回显。


def test_playground_supports_gateway_proxy_track():
    """页面必须能填网关 Host / ticket，并把业务请求改写成同源代理路径。"""
    text = _playground_text()
    assert 'value="proxy"' in text
    assert 'id="gatewayHost"' in text
    assert 'id="gatewayTicket"' in text
    assert "testGateway" in text
    assert "refreshWhoami" in text
    assert "/playground/proxy/session" in text
    # 业务请求必须统一经 apiUrl 改写，WS 经 wsUrl —— 不允许残留第二套 URL 拼接
    assert "function apiUrl(" in text
    assert "function wsUrl(" in text
    assert "fetch(apiUrl('/files')" in text
    assert "fetch(apiUrl('/runs')" in text
    assert "new WebSocket(wsUrl(runId))" in text


def test_proxy_session_binds_gateway_and_ticket():
    from lca.plugins.transport.webserver.routes_mangli_playground import (
        reset_proxy_sessions,
    )

    reset_proxy_sessions()
    client = _client()

    ok = client.post(
        "/playground/proxy/session",
        json={"gateway": "https://gw.company.com/", "ticket": "TKT-1"},
    )
    assert ok.status_code == 200
    body = ok.json()
    # 尾斜杠必须归一，否则 target 拼接会出现 "//health"
    assert body["gateway"] == "https://gw.company.com"
    assert body["ticket_present"] is True
    assert body["session_id"]

    for bad in ("", "gw.company.com", "ftp://gw.company.com", "https:///x"):
        res = client.post("/playground/proxy/session", json={"gateway": bad})
        assert res.status_code == 400, bad
        assert res.json()["error"]["code"] == "invalid_gateway"


def test_proxy_rejects_request_without_session():
    from lca.plugins.transport.webserver.routes_mangli_playground import (
        reset_proxy_sessions,
    )

    reset_proxy_sessions()
    res = _client().get("/playground/proxy/health")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "proxy_session_missing"


def test_proxy_injects_ticket_and_drops_identity_headers():
    """转发只带业务头 + ticket：cookie / Authorization / 身份头一律丢弃。

    这条是防止「页面借代理伪造身份」的回归：中间件在网关轨会剥离这些头，
    代理也必须做同样的事，否则两条链路行为不一致。
    """
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from lca.plugins.transport.webserver.routes_mangli_playground import (
        reset_proxy_sessions,
    )

    seen: dict = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("content-length") or 0)
            seen["path"] = self.path
            seen["headers"] = {k.lower(): v for k, v in self.headers.items()}
            seen["body"] = self.rfile.read(length).decode()
            payload = json.dumps({"run_id": "run_1"}).encode()
            self.send_response(202)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        reset_proxy_sessions()
        client = _client()
        gateway = f"http://127.0.0.1:{server.server_address[1]}"
        session = client.post(
            "/playground/proxy/session", json={"gateway": gateway, "ticket": "TKT-1"}
        ).json()

        res = client.post(
            "/playground/proxy/runs",
            headers={
                "x-playground-session": session["session_id"],
                "cookie": "portal=secret",
                "authorization": "Bearer forged",
                "x-lca-user-id": "99999",
                "content-type": "application/json",
            },
            content=b'{"messages":[]}',
        )

        assert res.status_code == 202
        assert res.json()["run_id"] == "run_1"
        assert seen["path"] == "/runs"
        assert seen["headers"]["ticket"] == "TKT-1"
        assert seen["body"] == '{"messages":[]}'
        for dropped in ("cookie", "authorization", "x-lca-user-id", "x-playground-session"):
            assert dropped not in seen["headers"], dropped
    finally:
        server.shutdown()
        server.server_close()


def test_ws_proxy_reports_missing_session():
    """没有 session 就明确回 auth_failed，而不是让页面干等握手超时。"""
    from starlette.applications import Starlette
    from starlette.routing import WebSocketRoute

    from lca.plugins.transport.webserver.routes_mangli_playground import (
        PROXY_WS_PATH,
        playground_proxy_ws,
        reset_proxy_sessions,
    )

    reset_proxy_sessions()
    app = Starlette(routes=[WebSocketRoute(PROXY_WS_PATH, playground_proxy_ws)])
    with TestClient(app).websocket_connect("/playground/proxy/v1/runs/run_1/ws") as ws:
        message = ws.receive_json()
    assert message["type"] == "auth_failed"
    assert "session" in message["reason"]


def test_ws_proxy_injects_ticket_and_relays_frames():
    """WS 代理必须带 ticket 连网关，并双向搬运帧。

    回归保护：浏览器无法给 ``new WebSocket`` 加请求头，ticket 只能在服务端
    握手时注入；一旦漏掉，网关会直接拒绝升级，页面表现成 WS 永远离线。
    """
    import asyncio
    import threading

    import websockets
    from starlette.applications import Starlette
    from starlette.routing import WebSocketRoute

    from lca.plugins.transport.webserver.routes_mangli_playground import (
        PROXY_WS_PATH,
        create_proxy_session,
        playground_proxy_ws,
        reset_proxy_sessions,
    )

    seen: dict = {}
    ready = threading.Event()

    async def _upstream(connection):
        seen["ticket"] = connection.request.headers.get("ticket")
        async for message in connection:
            await connection.send(f"echo:{message}")

    async def _serve() -> None:
        async with websockets.serve(_upstream, "127.0.0.1", 0) as server:
            seen["port"] = server.sockets[0].getsockname()[1]
            ready.set()
            await asyncio.Future()

    threading.Thread(target=lambda: asyncio.run(_serve()), daemon=True).start()
    assert ready.wait(5), "upstream ws server did not start"

    reset_proxy_sessions()
    session = create_proxy_session(f"http://127.0.0.1:{seen['port']}", "TKT-WS")
    app = Starlette(routes=[WebSocketRoute(PROXY_WS_PATH, playground_proxy_ws)])

    with TestClient(app).websocket_connect(
        f"/playground/proxy/v1/runs/run_1/ws?x-playground-session={session.session_id}"
    ) as ws:
        ws.send_text("hello")
        assert ws.receive_text() == "echo:hello"

    assert seen["ticket"] == "TKT-WS"


def test_whoami_without_principal():
    res = _client().get("/whoami")
    assert res.status_code == 200
    assert res.json()["authenticated"] is False


def test_whoami_reports_injected_identity_without_pii():
    """身份回显只给 userId 与字段名：姓名手机号不能落到免鉴权可读的响应里。"""
    from starlette.applications import Starlette

    from lca.plugins.transport.webserver.handlers.auth.principal import Principal
    from lca.plugins.transport.webserver.routes_mangli_playground import (
        playground_whoami_endpoint,
    )

    class _InjectPrincipal:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            scope.setdefault("state", {})["principal"] = Principal(
                issuer="mangli",
                subject="10001",
                user_id="10001",
                name="张三",
                mobile="13800138000",
                job_number="E10001",
                ticket="TKT-1",
            )
            await self.app(scope, receive, send)

    app = Starlette()
    app.add_route("/whoami", playground_whoami_endpoint, methods=["GET"])
    app.add_middleware(_InjectPrincipal)

    body = TestClient(app).get("/whoami").json()
    assert body["authenticated"] is True
    assert body["userId"] == "10001"
    assert body["issuer"] == "mangli"
    assert body["ticket_present"] is True
    assert "job_number" in body["fields"]
    assert "张三" not in json.dumps(body, ensure_ascii=False)
    assert "13800138000" not in json.dumps(body)
