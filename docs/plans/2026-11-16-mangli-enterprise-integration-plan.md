# 企业级应用集成与统一接口封装实施计划 (Mangli Enterprise Integration Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于 LCA 插件化微内核，在零修改底层核心代码的前提下，构建自适应双轨鉴权中间件（无侵入兼容 LobeHub 原生测试与公司 Gateway 鉴权）、多租户 Run 并发去重隔离安全防护、Projects 存储引擎（SQLite/Postgres 双后端）、增量项目路由与会话项目关联扩展、真实的 Tool 协议与 MCP 集群配置，以及纯内网离线自包含的 Playground 验证单页。

**Architecture:** 纯外围插件扩展（Seam/Provider 范式）。全盘复用成熟的原生端点（`/runs`、`/v1/runs/{id}/ws`、`/files`、`/v1/models` 等），不建平行 URL 副本；通过在 `server.py` 挂载 `SmartAdaptiveAuthMiddleware` 智能识别流量并完成身份桥接；修复 Transport 层的多租户并发去重隔离；外部数据通过原生 `mcp_servers` 声明式挂载；增量提供企业级 `Projects` 与 `Sessions` 存储与管理服务。

**Tech Stack:** Python 3.12, Starlette, Pydantic, Cryptography (AES-ECB-PKCS7), HTTPX (Async Permissions), WebSocket, SQLite3, HTML5/Native CSS (离线自包含).

---

### Task 1: 智能自适应鉴权中间件与服务挂载 (M4, M7, M8)

**Files:**
- Create: `lca/plugins/transport/webserver/handlers/auth/mangli_auth.py`
- Modify: `lca/plugins/transport/webserver/server/server.py` (安装中间件 Seam)
- Test: `tests/plugins/transport/test_mangli_auth.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-01: Java 原生编译运行生成的静态密文向量解密一致性（固定 Java 三元组：Plaintext, Key, Hex Ciphertext）；
  - INV-02: 权限微服务异步调用，纯标准库实现的 `ExpiringLruCache` 5 分钟 TTL 缓存命中与网络容灾降级；
  - INV-03: 自适应双轨鉴权：无 `X-Mangli-User` 时 LobeHub 100% 原样放行，LobeHub 测试 0 影响；有 `X-Mangli-User` 时自动解密并桥接注入底层 `user_id`。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_mangli_auth.py
import pytest
from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
    ExpiringLruCache,
    MangliAuthService,
    SmartAdaptiveAuthMiddleware,
    decrypt_mangli_user_header,
    derive_sha1prng_key,
    encrypt_mangli_user_header_for_test,
)


def test_java_cross_compatibility_vector():
  # 固定 Java 向量三元组 (对齐标准 Java Cipher.getInstance("AES/ECB/PKCS5Padding"))
  key_hex = "0123456789abcdef0123456789abcdef"
  key = bytes.fromhex(key_hex)
  expected_cipher_hex = "39b8a117fb5afc5bde07945964f2c2b8bb1fdd7c43d44d40336c864cbf7accea01c34f86851bc289a5acd8e9d953c24cdff6f07e6a20d89b8f5fde7ca6eab628"

  info = decrypt_mangli_user_header(expected_cipher_hex, key)
  assert info["user_id"] == "U888"
  assert info["name"] == "zhangsan"
  assert info["dept_id"] == "D01"

  # 测试动态自测加密工具的一致性
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
    return ["user:read", "project:access"], ["engineer"]

  service = MangliAuthService(fetch_fn=mock_fetch_permissions)
  perms, roles = await service.get_permissions("ticket_123", "U1001")
  assert call_count == 1
  assert "user:read" in perms

  # 命中 5min 缓存
  perms2, roles2 = await service.get_permissions("ticket_123", "U1001")
  assert call_count == 1
  assert perms2 == perms


@pytest.mark.asyncio
async def test_adaptive_auth_double_track():
  captured_headers = {}

  async def dummy_app(scope, receive, send):
    nonlocal captured_headers
    captured_headers = dict(scope.get("headers", []))

  mw = SmartAdaptiveAuthMiddleware(dummy_app)

  # 1. 无 X-Mangli-User (LobeHub 流量)：原封不动放行
  scope_lobehub = {
      "type": "http",
      "path": "/runs",
      "headers": [
          (b"x-lca-user-id", b"usr_lobe"),
          (b"authorization", b"Bearer lca-local"),
      ],
  }
  await mw(scope_lobehub, None, None)
  assert captured_headers.get(b"x-lca-user-id") == b"usr_lobe"

  # 2. 有 X-Mangli-User (公司 Gateway 流量)：自动解密并桥接为底层 x-lca-user-id
  key = bytes.fromhex("0123456789abcdef0123456789abcdef")
  enc = encrypt_mangli_user_header_for_test(
      '{"user_id":"U888","name":"zhangsan","dept_id":"D01"}', key
  )
  scope_gateway = {
      "type": "http",
      "path": "/runs",
      "headers": [(b"x-mangli-user", enc.encode()), (b"ticket", b"t123")],
  }
  await mw(scope_gateway, None, None)
  assert captured_headers.get(b"x-lca-user-id") == b"U888"
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/plugins/transport/test_mangli_auth.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`.

**Step 3: Write minimal implementation**
- 实现 `lca/plugins/transport/webserver/handlers/auth/mangli_auth.py`：
  - `derive_sha1prng_key(password: bytes) -> bytes`；
  - `decrypt_mangli_user_header(hex_str: str, key: bytes) -> dict` 与 `encrypt_mangli_user_header_for_test(...)`；
  - `ExpiringLruCache`（纯标准库 `collections.OrderedDict` + `time.monotonic()`）；
  - `MangliAuthService`；
  - `SmartAdaptiveAuthMiddleware` 与 `install_adaptive_auth_middleware(app)`；
- 修改 `lca/plugins/transport/webserver/server/server.py`：在 `install_trace_middleware(app)` 旁调用 `install_adaptive_auth_middleware(app)`。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/plugins/transport/test_mangli_auth.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/handlers/auth/mangli_auth.py lca/plugins/transport/webserver/server/server.py tests/plugins/transport/test_mangli_auth.py
git commit -m "feat(auth): implement smart adaptive auth middleware and mount seam in server"
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
    RunSessionIndex,
    run_dedup_key,
)


def test_multitenant_inflight_run_dedup_isolation():
  # 两个不同用户发送完全相同的提问与参数
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

  # 必须产生不同的去重指纹，杜绝跨租户请求合并与数据泄露
  assert key_user_a != key_user_b
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/plugins/transport/test_multitenant_inflight_run_dedup.py -v`
Expected: FAIL (TypeError: `run_dedup_key() got an unexpected keyword argument 'user_id'`).

**Step 3: Write minimal implementation**
- 修改 `lca/plugins/transport/webserver/handlers/runs/session/index/index.py`：
  - `run_dedup_key` 签名增加 `user_id: str = ""`，哈希 payload 增加 `user_id`；
  - `_session_dedup_key` 提取 `session.user_id`；
  - `find_inflight_run` 签名增加 `user_id: str = ""` 并传递给 `run_dedup_key`；
- 修改 `lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py`：
  - `create_and_dispatch` 在调用 `find_inflight_run` 时传入 `user_id=request.user_id`。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/plugins/transport/test_multitenant_inflight_run_dedup.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/handlers/runs/session/index/index.py lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py tests/plugins/transport/test_multitenant_inflight_run_dedup.py
git commit -m "fix(security): incorporate user_id into in-flight run dedup to prevent multi-tenant data leak"
```

---

### Task 3: Projects 领域模型与存储引擎实现 (M8)

**Files:**
- Create: `lca/infrastructure/persistence/project_store.py`
- Test: `tests/plugins/persistence/test_project_store.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-05: Projects 实体与 `project_id ↔ session_id` 映射；支持游离会话（`project_id is None`）；支持按拥有者与部门的访问隔离。

**Step 1: Write the failing test**

```python
# tests/plugins/persistence/test_project_store.py
import pytest
from lca.infrastructure.persistence.project_store import ProjectStore


def test_project_isolation_and_unassigned_sessions(tmp_path):
  db_path = tmp_path / "test_projects.sqlite3"
  store = ProjectStore(db_url=f"sqlite:///{db_path}")

  # 1. 创建项目
  proj = store.create_project(
      name="数据分析专案",
      description="华东区销售分析",
      owner_user_id="U1001",
      dept_id="D01",
  )
  assert proj.project_id.startswith("proj_")

  # 2. 隔离性测试
  user1_projects = store.list_projects(user_id="U1001", dept_id="D01")
  user2_projects = store.list_projects(user_id="U2002", dept_id="D99")
  assert len(user1_projects) == 1
  assert len(user2_projects) == 0

  # 3. 关联会话与查询
  store.bind_session(
      project_id=proj.project_id, session_id="sess_123", user_id="U1001"
  )
  sessions = store.get_project_sessions(project_id=proj.project_id)
  assert "sess_123" in sessions

  # 4. 创建个人游离会话 (无 project_id)
  store.create_unassigned_session(session_id="sess_free", user_id="U1001")
  unassigned = store.list_unassigned_sessions(user_id="U1001")
  assert "sess_free" in unassigned
  assert "sess_123" not in unassigned
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/plugins/persistence/test_project_store.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
实现 `lca/infrastructure/persistence/project_store.py`：
- 定义 SQLite DDL（`lca_projects`, `lca_project_sessions`）；
- 实现 `ProjectStore`：`create_project`, `list_projects`, `get_project`, `delete_project`, `bind_session`, `unbind_session`, `get_project_sessions`, `create_unassigned_session`, `list_unassigned_sessions`。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/plugins/persistence/test_project_store.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/infrastructure/persistence/project_store.py tests/plugins/persistence/test_project_store.py
git commit -m "feat(persistence): implement ProjectStore with multi-tenant isolation and unassigned sessions"
```

---

### Task 4: Projects 与企业会话路由插件 (M3)

**Files:**
- Create: `lca/plugins/transport/webserver/routes_mangli_projects.py`
- Test: `tests/plugins/transport/test_routes_mangli_projects.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - 增量挂载 `GET/POST /projects`、`GET/DELETE /projects/{id}`、`GET/POST /projects/{id}/sessions`、`GET/POST /sessions`；
  - 插件声明严格包含 `layer="L1"`, `kind=PluginKind.PROVIDER`, `effects="none"`, `contract=PluginContract(...)`, `ownership=OwnershipDeclaration(...)`。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_routes_mangli_projects.py
import pytest
from starlette.testclient import TestClient


def test_projects_route_specs_exist():
  from lca.plugins.transport.webserver.routes_mangli_projects import (
      PROJECTS_ROUTE_SPECS,
  )

  paths = {spec.path for spec in PROJECTS_ROUTE_SPECS}
  assert "/projects" in paths
  assert "/projects/{project_id}" in paths
  assert "/projects/{project_id}/sessions" in paths
  assert "/sessions" in paths
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/plugins/transport/test_routes_mangli_projects.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
实现 `lca/plugins/transport/webserver/routes_mangli_projects.py`：
- 声明 `PROJECTS_ROUTE_SPECS` 包含 `/projects`、`/projects/{project_id}`、`/projects/{project_id}/sessions`、`/sessions` 处理函数；
- 按照官方标准声明 `@plugin` 完整参数：`layer="L1"`, `kind=PluginKind.PROVIDER`, `effects="none"`, `contract=...`, `ownership=...`；
- `setup(ctx)` 向 `route_registry` 注册上述路由。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/plugins/transport/test_routes_mangli_projects.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/routes_mangli_projects.py tests/plugins/transport/test_routes_mangli_projects.py
git commit -m "feat(transport): register mangli projects and enterprise sessions routes plugin"
```

---

### Task 5: 真实 LCA Tool 契约实现与企业能力 (M5, M6)

**Files:**
- Create: `lca/plugins/tools/mangli_enterprise_tools.py`
- Test: `tests/plugins/tools/test_mangli_enterprise_tools.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-06: 严格继承 LCA `Tool(Protocol)`，声明 `name`, `namespace`, `description`, `parameters`, `is_idempotent`, `effect_kind`, `default_timeout_s`；
  - 模型暴露的 `parameters` 绝对不含 `project_id`/`session_id`；
  - 文件生成调用 `FileStore.put(..., origin="agent_created")`，返回包含下载链接的 `Observation`；
  - 注册机制走 `tools_seam.register_factory`。

**Step 1: Write the failing test**

```python
# tests/plugins/tools/test_mangli_enterprise_tools.py
from typing import Any
import pytest
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.infrastructure.file.store import InMemoryFileStore
from lca.plugins.tools.mangli_enterprise_tools import MangliWorkspaceExportTool


@pytest.mark.asyncio
async def test_tool_conforms_to_lca_contract():
  file_store = InMemoryFileStore()
  # 租户上下文在构建/注入时确定，模型参数不可控
  tool = MangliWorkspaceExportTool(
      file_store=file_store,
      user_id="U888",
      project_id="proj_01",
      session_id="sess_01",
  )

  # 1. 契约符合性
  assert isinstance(tool, Tool)
  assert tool.name == "mangli_workspace_export"
  assert tool.namespace == "workspace"
  assert "project_id" not in tool.parameters["properties"]
  assert "session_id" not in tool.parameters["properties"]

  # 2. 执行并生成 Observation
  obs = await tool.execute({"path": "report.txt", "content": "hello mangli"})
  assert isinstance(obs, Observation)
  assert obs.payload["status"] == "ok"
  assert "attachment_id" in obs.payload
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/plugins/tools/test_mangli_enterprise_tools.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
实现 `lca/plugins/tools/mangli_enterprise_tools.py`：
- 严格遵循 `Tool(Protocol)` 实现 `MangliWorkspaceExportTool`；
- 文件通过 `FileStore.put(..., origin="agent_created")` 持久化，返回标准 `Observation`；
- 提供 `register_mangli_tools_factory(tools_seam, bindings)` 工厂函数；
- 实现标准的 `@plugin` 声明以挂载工具工厂。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/plugins/tools/test_mangli_enterprise_tools.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/tools/mangli_enterprise_tools.py tests/plugins/tools/test_mangli_enterprise_tools.py
git commit -m "feat(tools): implement enterprise export tool conforming to Tool protocol and FileStore"
```

---

### Task 6: 离线自包含的 Playground 验证控制台 (M8)

**Files:**
- Create: `lca/plugins/transport/webserver/static/mangli_playground.html`
- Test: `tests/plugins/transport/test_mangli_playground.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-07: 纯原生现代化 CSS，无外网 CDN，内网离线自包含；
  - `GET /playground` 路由正常响应 200 并返回该 HTML 内容。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_mangli_playground.py
from pathlib import Path
import pytest
from starlette.requests import Request
from starlette.responses import HTMLResponse


def test_playground_offline_render():
  html_path = (
      Path("lca/plugins/transport/webserver/static/mangli_playground.html")
  )
  assert html_path.exists(), "Playground html must exist"

  content = html_path.read_text(encoding="utf-8")
  # 验证离线自包含：绝不含任何外部 CDN 链接
  assert "cdn.tailwindcss.com" not in content
  assert "unpkg.com" not in content
  assert "<style>" in content
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/plugins/transport/test_mangli_playground.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 创建 `lca/plugins/transport/webserver/static/mangli_playground.html`：
  - 纯原生自包含 CSS；
  - 提供模式 A（公司 Gateway 模式）与模式 B（LobeHub 原生模式）双轨调试控制台；
  - 原生 WebSocket 监听 `/v1/runs/{run_id}/ws` 打字机流与 `/projects` 会话管理；
- 在 `routes_mangli_projects.py` 中挂载 `GET /playground` 路由。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/plugins/transport/test_mangli_playground.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/static/mangli_playground.html tests/plugins/transport/test_mangli_playground.py
git commit -m "feat(ui): add self-contained offline playground single page"
```

---

### Task 7: 声明式编排配置与真实 Merge-Base 零修改门禁 (M1, M2, M3, M7)

**Files:**
- Create: `bundles/mangli-enterprise.yaml`
- Create: `profiles/mangli-enterprise.yaml`
- Test: `tests/scenario/test_mangli_enterprise_bundle_invariants.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-08: **分支基线零修改铁律**：`git diff --name-only origin/main...HEAD -- lca/contracts lca/cognition lca/runtime lca/loop lca/framework lca_kernel vendor` 退出码必为 0 且输出必为空！
  - Profile 能够通过 `lca.harness.profile.resolve.resolve_profile` 成功解析，包含完整的 Web 和认知循环 14 个基础 bundle 与新增的 mangli bundle。

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
  plugin_ids = {entry["id"] for entry in resolved.entries}
  assert "mangli-enterprise-routes" in plugin_ids
  assert "mangli-enterprise-tools" in plugin_ids
  assert "lca-webserver-router" in plugin_ids
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/scenario/test_mangli_enterprise_bundle_invariants.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 编写 `bundles/mangli-enterprise.yaml`（采用规范的 `entries:` 语法）；
- 编写 `profiles/mangli-enterprise.yaml`（挂载 `profiles/web-standard.yaml` 的全量 14 个 bundle 并追加 `mangli-enterprise.yaml`）。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/scenario/test_mangli_enterprise_bundle_invariants.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add bundles/mangli-enterprise.yaml profiles/mangli-enterprise.yaml tests/scenario/test_mangli_enterprise_bundle_invariants.py
git commit -m "feat(orchestration): declare mangli-enterprise bundle and profile with zero core mutation guard"
```
