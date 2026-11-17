# 企业级应用集成与统一接口封装实施计划 (Mangli Enterprise Integration Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于 LCA 插件化微内核，在零修改底层核心代码的前提下，构建自适应双轨鉴权中间件（无侵入兼容 LobeHub 原生测试与公司 Gateway 鉴权）、标准 `Principal` 身份模型、多租户 Run 并发去重隔离安全防护、真实的 Tool 协议与 MCP 集群配置、纯内网离线自包含的 Playground 验证单页，并完成 Projects 领域能力的前瞻性架构预留。

**Architecture:** 纯外围插件扩展（Seam/Provider 范式）。全盘复用成熟的原生端点（`/runs`、`/v1/runs/{id}/ws`、`/files`、`/v1/models` 等），不建平行 URL 副本；通过在 `server.py` 挂载 `SmartAdaptiveAuthMiddleware` 智能识别流量、剥离伪造头并完成身份桥接；修复 Transport 层的多租户并发去重隔离；外部数据通过原生 `mcp_servers` 声明式挂载；实体归属严格遵循方案 A（LCA 不建 ProjectStore）。

**Tech Stack:** Python 3.12, Starlette, Pydantic (frozen + extra="forbid"), Cryptography (AES-ECB-PKCS7), HTTPX (Async Permissions), WebSocket (First-frame JWT), HTML5/Native CSS (离线自包含).

---

### Task 1: 标准 Principal 模型、智能自适应鉴权中间件与服务挂载 (M4, M7, M8, N1, N2, N6, N7, N8, R1, R3, R5, R16, R18)

**Files:**
- Create: `lca/plugins/transport/webserver/handlers/auth/principal.py`
- Create: `lca/plugins/transport/webserver/handlers/auth/mangli_auth.py`
- Modify: `lca/plugins/transport/webserver/server/server.py` (在 `install_trace_middleware` 之前挂载中间件 Seam)
- Test: `tests/plugins/transport/test_mangli_auth.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-01: Java 原生编译运行生成的静态密文向量解密一致性（固定 Java 三元组：Plaintext, Key, Hex Ciphertext）；
  - INV-02: 权限微服务 5 分钟 TTL 缓存命中与 Fail-Closed 阻断（服务不可用时严禁放行，返回 502；ticket 错误返回 401）；
  - INV-03: 自适应双轨鉴权与安全防护：
    - 公司网关流量：解密 `X-Mangli-User`，**强制剥离伪造头**（`x-lca-user-id`, `authorization`, `x-lca-token`），注入合法 `x-lca-user-id` 与 `Authorization: Bearer <expected_token>`，绑定 `Principal` 到 ContextVar；
    - 内网直连流量：在生产配置（`dev_mode=False`）下，缺少合法 Bearer 直接返回 401，阻断任意冒充。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_mangli_auth.py
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

  # 命中 5min 缓存
  perms2, roles2 = await service.get_permissions("ticket_123", "U1001")
  assert call_count == 1
  assert perms2 == perms

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
    lca_auth_expected_token = "secret-token-123"
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
    lca_auth_expected_token = "secret-token-123"
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
```

**Step 2: Run test to verify it fails**
Run: `.\.venv\Scripts\pytest tests/plugins/transport/test_mangli_auth.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 实现 `lca/plugins/transport/webserver/handlers/auth/principal.py`：定义 `Principal` 模型；
- 实现 `lca/plugins/transport/webserver/handlers/auth/mangli_auth.py`：
  - 加解密与标准库 LRU 缓存；
  - 伪造头剥离逻辑（`FORBIDDEN_CLIENT_HEADERS`）；
  - `SmartAdaptiveAuthMiddleware` 与 `install_adaptive_auth_middleware(app)`；
- 修改 `lca/plugins/transport/webserver/server/server.py`：在 `install_trace_middleware(app)` 之前调用 `install_adaptive_auth_middleware(app)`。

**Step 4: Run test to verify it passes**
Run: `.\.venv\Scripts\pytest tests/plugins/transport/test_mangli_auth.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/handlers/auth/principal.py lca/plugins/transport/webserver/handlers/auth/mangli_auth.py lca/plugins/transport/webserver/server/server.py tests/plugins/transport/test_mangli_auth.py
git commit -m "feat(auth): implement Principal model, adaptive auth middleware and install in server"
```

---

### Task 2: 多租户 In-Flight Run 并发去重隔离安全修复 (M9)

**Files:**
- Modify: `lca/plugins/transport/webserver/handlers/runs/session/index/index.py`
- Modify: `lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py`
- Test: `tests/plugins/transport/test_multitenant_inflight_run_dedup.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-04: 多租户并发去重隔离：不同用户发送相同内容的提问，计算出的 In-flight 指纹必须不同，绝不合并进同一 Run。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_multitenant_inflight_run_dedup.py
import pytest
from lca.plugins.transport.webserver.handlers.runs.session.index.index import (
    run_dedup_key,
)


def test_multitenant_inflight_run_dedup_isolation():
  key_user_a = run_dedup_key(
      user_id="user_A",
      user_text="查上月华东区销售额",
      mode="solo",
      agent_id="asst_1",
  )
  key_user_b = run_dedup_key(
      user_id="user_B",
      user_text="查上月华东区销售额",
      mode="solo",
      agent_id="asst_1",
  )
  assert key_user_a != key_user_b
```

**Step 2: Run test to verify it fails**
Run: `.\.venv\Scripts\pytest tests/plugins/transport/test_multitenant_inflight_run_dedup.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 修改 `lca/plugins/transport/webserver/handlers/runs/session/index/index.py`：`run_dedup_key` 与 `find_inflight_run` 引入 `user_id`；
- 修改 `lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py`：`create_and_dispatch` 传参 `user_id=request.user_id`。

**Step 4: Run test to verify it passes**
Run: `.\.venv\Scripts\pytest tests/plugins/transport/test_multitenant_inflight_run_dedup.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/handlers/runs/session/index/index.py lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py tests/plugins/transport/test_multitenant_inflight_run_dedup.py
git commit -m "fix(security): incorporate user_id into in-flight run dedup to prevent multi-tenant data leak"
```

---

### Task 3: 真实 LCA Tool 契约实现与企业能力 (M5, M6, R8)

**Files:**
- Create: `lca/plugins/tools/mangli_enterprise_tools.py`
- Test: `tests/plugins/tools/test_mangli_enterprise_tools.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-05: 严格继承 LCA `Tool(Protocol)`，声明 7 项 ClassVar；模型参数不暴露租户 ID；文件写入通过真实 `LocalFileStore` 生成不可变凭证；钉死 `@plugin(id="mangli-enterprise-tools")`。

**Step 1: Write the failing test**

```python
# tests/plugins/tools/test_mangli_enterprise_tools.py
from typing import Any
import pytest
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.tools.mangli_enterprise_tools import MangliWorkspaceExportTool


@pytest.mark.asyncio
async def test_tool_conforms_to_lca_contract(tmp_path):
  file_store = LocalFileStore(tmp_path / "files")
  tool = MangliWorkspaceExportTool(
      file_store=file_store,
      user_id="U888",
      project_id="proj_reserved_01",
      session_id="sess_01",
  )

  # 1. 契约符合性（7 项 ClassVar 必验）
  assert isinstance(tool, Tool)
  assert tool.name == "mangli_workspace_export"
  assert tool.namespace == "workspace"
  assert isinstance(tool.description, str)
  assert isinstance(tool.parameters, dict)
  assert isinstance(tool.is_idempotent, bool)
  assert tool.effect_kind in ("ephemeral", "persistent", "stateful_once")
  assert isinstance(tool.default_timeout_s, int)

  # 2. 租户参数严禁暴露在模型参数中
  assert "project_id" not in tool.parameters["properties"]
  assert "session_id" not in tool.parameters["properties"]

  # 3. 执行并生成 Observation 与 FileStore 凭证
  obs = await tool.execute({"path": "report.txt", "content": "hello mangli"})
  assert isinstance(obs, Observation)
  assert obs.payload["status"] == "ok"
  assert "attachment_id" in obs.payload
```

**Step 2: Run test to verify it fails**
Run: `.\.venv\Scripts\pytest tests/plugins/tools/test_mangli_enterprise_tools.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
实现 `lca/plugins/tools/mangli_enterprise_tools.py`：
- 严格遵循 `Tool(Protocol)` 实现 `MangliWorkspaceExportTool`；
- 文件持久化至 `LocalFileStore`；
- 声明标准的 `@plugin(id="mangli-enterprise-tools", layer="L1", kind=PluginKind.PROVIDER, effects="none", ...)` 挂载工具工厂。

**Step 4: Run test to verify it passes**
Run: `.\.venv\Scripts\pytest tests/plugins/tools/test_mangli_enterprise_tools.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/tools/mangli_enterprise_tools.py tests/plugins/tools/test_mangli_enterprise_tools.py
git commit -m "feat(tools): implement enterprise export tool conforming to Tool protocol and LocalFileStore"
```

---

### Task 4: 离线自包含的 Playground 验证控制台 (M8, R6, R7, R17)

**Files:**
- Create: `lca/plugins/transport/webserver/static/mangli_playground.html`
- Create: `lca/plugins/transport/webserver/routes_mangli_playground.py`
- Test: `tests/plugins/transport/test_mangli_playground.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-06: 纯原生自包含 CSS，无外网 CDN，内网离线渲染；钉死 `@plugin(id="mangli-enterprise-playground-route")`；通过 `TestClient` 发起真实的 `GET /playground` 严格返回 200 HTTP 响应。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_mangli_playground.py
import pytest
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
  assert 'type: "auth"' in res.text
```

**Step 2: Run test to verify it fails**
Run: `.\.venv\Scripts\pytest tests/plugins/transport/test_mangli_playground.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 创建 `lca/plugins/transport/webserver/static/mangli_playground.html`：
  - 纯原生自包含 CSS；
  - 严格遵循 LCA WebSocket 原生协议：建连后发送第一帧 `{"type": "auth", "token": ws_token}`，每 30s 发送心跳帧 `{"type": "heartbeat"}`；
- 创建 `lca/plugins/transport/webserver/routes_mangli_playground.py`：
  - 钉死 `@plugin(id="mangli-enterprise-playground-route", layer="L1", kind=PluginKind.PROVIDER, effects="none", ...)` 挂载 `GET /playground` 路由。

**Step 4: Run test to verify it passes**
Run: `.\.venv\Scripts\pytest tests/plugins/transport/test_mangli_playground.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/static/mangli_playground.html lca/plugins/transport/webserver/routes_mangli_playground.py tests/plugins/transport/test_mangli_playground.py
git commit -m "feat(ui): add self-contained offline playground single page and route plugin"
```

---

### Task 5: 声明式编排配置与真实 Merge-Base 零修改门禁 (M1, M2, M3, M7, R2, R7)

**Files:**
- Create: `bundles/mangli-enterprise.yaml`
- Create: `profiles/mangli-enterprise.yaml`
- Test: `tests/scenario/test_mangli_enterprise_bundle_invariants.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-07: **分支基线零修改铁律**：`git diff --name-only origin/main...HEAD -- lca/contracts lca/cognition lca/runtime lca/loop lca/framework lca_kernel vendor` 退出码必为 0 且输出必为空！
  - Profile 成功解析（包含 14 生产 bundle + `assistant-runtime.yaml` + mangli bundle），且通过 `{p.id for p in resolved.plugins}` 准确断言两个 mangli 插件 ID，关闭生产 dev_mode。

**Step 1: Write the failing test**

```python
# tests/scenario/test_mangli_enterprise_bundle_invariants.py
from pathlib import Path
import subprocess
import pytest
from lca.harness.profile.resolve.resolve import resolve_profile


def test_core_zero_mutation_against_merge_base():
  cmd = [
      "git",
      "diff",
      "--name-only",
      "origin/main...HEAD",
      "--",
      "lca/contracts",
      "lca/cognition",
      "lca/runtime",
      "lca/loop",
      "lca/framework",
      "lca_kernel",
      "vendor",
  ]
  res = subprocess.run(cmd, capture_output=True, text=True, check=True)
  assert res.stdout.strip() == "", (
      f"Core files were mutated against origin/main:\n{res.stdout}"
  )


def test_mangli_profile_resolves_cleanly():
  profile_path = Path("profiles/mangli-enterprise.yaml")
  assert profile_path.exists()
  resolved = resolve_profile(profile_path)
  # 正确使用 ResolvedProfile.plugins 数据契约
  plugin_ids = {p.id for p in resolved.plugins}
  assert "mangli-enterprise-playground-route" in plugin_ids
  assert "mangli-enterprise-tools" in plugin_ids
  assert "lca-webserver-router" in plugin_ids
```

**Step 2: Run test to verify it fails**
Run: `.\.venv\Scripts\pytest tests/scenario/test_mangli_enterprise_bundle_invariants.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 编写 `bundles/mangli-enterprise.yaml`（`entries:` 规范格式，声明两个插件条目）；
- 编写 `profiles/mangli-enterprise.yaml`（挂载全量生产 bundle，patch 声明 `dev_mode: false`）。

**Step 4: Run test to verify it passes**
Run: `.\.venv\Scripts\pytest tests/scenario/test_mangli_enterprise_bundle_invariants.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add bundles/mangli-enterprise.yaml profiles/mangli-enterprise.yaml tests/scenario/test_mangli_enterprise_bundle_invariants.py
git commit -m "feat(orchestration): declare mangli-enterprise bundle and profile with zero core mutation guard"
```
