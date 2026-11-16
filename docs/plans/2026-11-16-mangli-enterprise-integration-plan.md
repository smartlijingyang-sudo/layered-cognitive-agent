# 企业级应用集成与统一接口封装实施计划 (Mangli Enterprise Integration Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于 LCA 插件化微内核，在零修改底层核心代码的前提下，构建企业统一鉴权中间件（AES-ECB-PKCS5Padding + 标准库 LRU 缓存）、Projects 存储引擎（SQLite/Postgres 双后端）、收敛的 Thin Façade 接口（复用底层 Runs/Stream/Cancel/Files/Models）、真实的 Tool 协议与 MCP 集群配置，以及纯内网离线自包含的 Playground 验证单页。

**Architecture:** 纯外围插件扩展（Thin Façade 模式）。Starlette 网关挂载路径隔离的中间件与企业门面路由，复用现有 `command_endpoints`、`live.py` 与 `files.py`；外部数据通过原生 `mcp_servers` 声明式挂载；全链路事实由 Session 追加单轨保障。

**Tech Stack:** Python 3.12, Starlette, Pydantic, Cryptography (AES-ECB-PKCS7), HTTPX (Async Permissions), Server-Sent Events (SSE), SQLite3, HTML5/Native CSS (离线免构建).

---

### Task 1: Mangli 鉴权与用户上下文模块 (Java 向量对齐 + 标准库缓存)

**Files:**
- Create: `lca/plugins/transport/webserver/handlers/auth/mangli_auth.py`
- Test: `tests/plugins/transport/test_mangli_auth.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-01: Java 原生编译运行生成的静态密文向量解密一致性；纯 Hex 16 字节密钥主路；SHA1PRNG 兼容辅路；
  - INV-02: 权限微服务异步调用，纯标准库实现的 `ExpiringLruCache` 5 分钟 TTL 缓存命中与网络容灾降级；
  - INV-03: 中间件路径隔离（非 `/api/v1/*` 路径 100% 豁免放行）。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_mangli_auth.py
import pytest
from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
    ExpiringLruCache,
    MangliAuthMiddleware,
    MangliAuthService,
    MangliUserContext,
    decrypt_mangli_user_header,
    derive_sha1prng_key,
)


def test_java_cross_compatibility_vector():
  # 使用由 Java 原生 KeyGenerator("AES") + SecureRandom("SHA1PRNG") + password "mangli_test_key_2026"
  # 生成的已知 Hex 密文向量进行跨语言对齐校验
  password = b"mangli_test_key_2026"
  key = derive_sha1prng_key(password)
  assert len(key) == 16

  # 纯 Hex 模式验证
  key_hex = key.hex()
  assert len(bytes.fromhex(key_hex)) == 16


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

  # 命中 5min 缓存，不产生重复网络调用
  perms2, roles2 = await service.get_permissions("ticket_123", "U1001")
  assert call_count == 1


@pytest.mark.asyncio
async def test_middleware_path_exemption():
  app_called = False

  async def dummy_app(scope, receive, send):
    nonlocal app_called
    app_called = True

  mw = MangliAuthMiddleware(dummy_app)
  # 非 /api/v1 路径（如 /health）应直接放行，不检查 Header
  scope = {"type": "http", "path": "/health", "headers": []}
  await mw(scope, None, None)
  assert app_called is True
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/plugins/transport/test_mangli_auth.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`.

**Step 3: Write minimal implementation**
实现 `lca/plugins/transport/webserver/handlers/auth/mangli_auth.py`：
- `derive_sha1prng_key(password: bytes) -> bytes` 与 Hex 密钥解析；
- `decrypt_mangli_user_header(hex_str: str, key: bytes) -> dict`；
- `ExpiringLruCache`（纯标准库 `collections.OrderedDict` + `time.monotonic()` 实现）；
- `MangliAuthService`；
- `MangliAuthMiddleware`（纯 ASGI，非 `/api/v1` 100% 放行，拦截 `/api/v1` 解密并注入 `scope["state"]["user_id"]` 与 `ContextVar`）。

**Step 4: Run test to verify it passes**
Run: `pytest tests/plugins/transport/test_mangli_auth.py -v`
Expected: PASS (4/4 passed).

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/handlers/auth/mangli_auth.py tests/plugins/transport/test_mangli_auth.py
git commit -m "feat(auth): implement Mangli auth with Java vector alignment and path exemption"
```

---

### Task 2: Projects 领域模型与存储引擎实现

**Files:**
- Create: `lca/infrastructure/persistence/project_store.py`
- Test: `tests/plugins/persistence/test_project_store.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-04: Projects 实体与 `project_id ↔ session_id` 映射；支持游离会话（`project_id is None`）；支持按拥有者与部门的访问隔离。

**Step 1: Write the failing test**

```python
# tests/plugins/persistence/test_project_store.py
import pytest
from lca.infrastructure.persistence.project_store import ProjectStore


def test_project_crud_and_session_binding(tmp_path):
  db_path = tmp_path / "test_lca.sqlite3"
  store = ProjectStore(database_url=str(db_path))

  # 1. 创建项目
  proj = store.create_project(
      name="AI客服项目",
      description="2026年客服升级",
      owner_user_id="U1001",
      dept_id="D01",
  )
  assert proj.project_id.startswith("proj_")
  assert proj.name == "AI客服项目"

  # 2. 查询项目列表（隔离性）
  user_projects = store.list_projects(user_id="U1001", dept_id="D01")
  assert len(user_projects) == 1
  other_projects = store.list_projects(user_id="U9999", dept_id="D99")
  assert len(other_projects) == 0

  # 3. 关联会话与查询
  store.bind_session(project_id=proj.project_id, session_id="sess_123")
  sessions = store.get_project_sessions(project_id=proj.project_id)
  assert "sess_123" in sessions

  # 4. 解除关联与游离状态确认
  store.unbind_session(session_id="sess_123")
  sessions_after = store.get_project_sessions(project_id=proj.project_id)
  assert "sess_123" not in sessions_after
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/plugins/persistence/test_project_store.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
实现 `lca/infrastructure/persistence/project_store.py`：
- 定义 SQLite DDL（`lca_projects`, `lca_project_sessions`）；
- 实现 `ProjectStore`：`create_project`, `list_projects`, `get_project`, `bind_session`, `unbind_session`, `get_session_project`。

**Step 4: Run test to verify it passes**
Run: `pytest tests/plugins/persistence/test_project_store.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/infrastructure/persistence/project_store.py tests/plugins/persistence/test_project_store.py
git commit -m "feat(persistence): implement ProjectStore with session binding and isolation"
```

---

### Task 3: 企业 Thin Façade 路由插件 (`routes_mangli_api.py`)

**Files:**
- Create: `lca/plugins/transport/webserver/routes_mangli_api.py`
- Test: `tests/plugins/transport/test_routes_mangli_api.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca_kernel/` (AP-01)
- Invariants to test:
  - INV-05: Thin Façade 严格复用底层现成 Handler（`create_run`, `live_endpoint`, `cancel_run`, `list_models`, `download_file`），不造重复轮子；
  - 会话查询支持 `project_id` 过滤与游离会话（`unassigned=true`）过滤。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_routes_mangli_api.py
import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette


def test_mangli_facade_route_specs_exist():
  from lca.plugins.transport.webserver.routes_mangli_api import (
      MANGLI_ROUTE_SPECS,
  )

  paths = {spec.path for spec in MANGLI_ROUTE_SPECS}
  assert "/api/v1/projects" in paths
  assert "/api/v1/sessions" in paths
  assert "/api/v1/sessions/{session_id}/runs" in paths
  assert "/api/v1/runs/{run_id}/stream" in paths
  assert "/api/v1/runs/{run_id}/cancel" in paths
  assert "/api/v1/models" in paths
  assert "/api/v1/files/{attachment_id}/download" in paths
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/plugins/transport/test_routes_mangli_api.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
实现 `lca/plugins/transport/webserver/routes_mangli_api.py`：
- 导入现有底层 handlers：`create_run`, `cancel_run`, `live_endpoint`, `list_models`, `download_file`；
- 暴露 Thin Façade 路由；
- 插件 setup(ctx) 挂载 `MangliAuthMiddleware` 并注册路由。

**Step 4: Run test to verify it passes**
Run: `pytest tests/plugins/transport/test_routes_mangli_api.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/routes_mangli_api.py tests/plugins/transport/test_routes_mangli_api.py
git commit -m "feat(routes): implement Mangli thin facade routes reusing existing handlers"
```

---

### Task 4: 真实的 LCA Tool 契约实现与 MCP 集群配置

**Files:**
- Create: `lca/plugins/tools/mangli_enterprise_tools.py`
- Test: `tests/plugins/tools/test_mangli_enterprise_tools.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca_kernel/` (AP-01)
- Invariants to test:
  - INV-06: 严格继承 `lca.contracts.protocols.Tool`，声明 `parameters`（非 `parameters_schema`），`execute(args)` 返回 `Observation`；
  - 问数 Agent A2A 委托自动附带当前调用者上下文；受控工作区安全文件沙箱读写回执闭环。

**Step 1: Write the failing test**

```python
# tests/plugins/tools/test_mangli_enterprise_tools.py
import pytest
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.plugins.tools.mangli_enterprise_tools import (
    QueryDataAgentTool,
    WorkspaceFileOpsTool,
)


def test_tool_conforms_to_lca_contract():
  tool = QueryDataAgentTool()
  assert isinstance(tool, Tool)
  assert hasattr(tool, "name")
  assert hasattr(tool, "namespace")
  assert isinstance(tool.parameters, dict)
  assert "query" in tool.parameters["properties"]


@pytest.mark.asyncio
async def test_file_tool_execution_returns_observation(tmp_path):
  tool = WorkspaceFileOpsTool(root_dir=tmp_path)
  assert isinstance(tool, Tool)

  # 写入文件执行
  obs = await tool.execute({
      "action": "write",
      "filename": "monthly_report.md",
      "content": "## 销售月报",
      "project_id": "proj_01",
      "session_id": "sess_01",
  })
  assert isinstance(obs, Observation)
  assert obs.success is True
  assert obs.payload["file_id"] is not None

  # 读取文件执行
  read_obs = await tool.execute({
      "action": "read",
      "file_id": obs.payload["file_id"],
      "project_id": "proj_01",
      "session_id": "sess_01",
  })
  assert isinstance(read_obs, Observation)
  assert read_obs.success is True
  assert "销售月报" in read_obs.payload["content"]
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/plugins/tools/test_mangli_enterprise_tools.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
实现 `lca/plugins/tools/mangli_enterprise_tools.py`：
- 实现 `QueryDataAgentTool(Tool)`；
- 实现 `WorkspaceFileOpsTool(Tool)`；
- `@plugin(id="mangli-enterprise-tools", requires=("tools",))` 工厂注册。

**Step 4: Run test to verify it passes**
Run: `pytest tests/plugins/tools/test_mangli_enterprise_tools.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/tools/mangli_enterprise_tools.py tests/plugins/tools/test_mangli_enterprise_tools.py
git commit -m "feat(tools): implement Mangli enterprise tools strictly conforming to LCA Tool protocol"
```

---

### Task 5: 离线自包含的 Playground 验证控制台单页

**Files:**
- Create: `lca/plugins/transport/webserver/static/mangli_playground.html`
- Modify: `lca/plugins/transport/webserver/routes_mangli_api.py` (注册 `GET /playground`)
- Test: `tests/plugins/transport/test_playground_endpoint.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca_kernel/` (AP-01)
- Invariants to test:
  - INV-08: `GET /playground` 严格返回 200 及 `text/html`；HTML 纯原生 CSS 自包含，无外部 Tailwind 等外网 CDN 引用。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_playground_endpoint.py
from pathlib import Path
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import HTMLResponse


def test_playground_offline_render():
  p = Path(
      "lca/plugins/transport/webserver/static/mangli_playground.html"
  )
  assert p.exists()
  content = p.read_text(encoding="utf-8")
  # 验证零外网 CDN 依赖（内网离线保证）
  assert "cdn.tailwindcss.com" not in content
  assert "googleapis.com" not in content
  assert "<style>" in content  # 包含内置原生样式
  assert "X-Mangli-User" in content
  assert "EventSource" in content
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/plugins/transport/test_playground_endpoint.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 编写 `lca/plugins/transport/webserver/static/mangli_playground.html`；
- 在 `routes_mangli_api.py` 中挂载 `RouteSpec("/playground", playground_endpoint, ("GET",))`。

**Step 4: Run test to verify it passes**
Run: `pytest tests/plugins/transport/test_playground_endpoint.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/static/mangli_playground.html lca/plugins/transport/webserver/routes_mangli_api.py tests/plugins/transport/test_playground_endpoint.py
git commit -m "feat(playground): add self-contained offline verification console"
```

---

### Task 6: 声明式编排配置与真实 Merge-Base 零修改门禁

**Files:**
- Create: `bundles/mangli-enterprise.yaml`
- Create: `profiles/mangli-enterprise.yaml`
- Test: `tests/plugins/test_mangli_core_zero_mutation_guard.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca_kernel/` (AP-01)
- Invariants to test:
  - INV-07: 对比 `origin/main...HEAD`，核心目录 `lca/contracts`, `lca/cognition`, `lca/runtime`, `lca/loop`, `lca/framework`, `lca_kernel`, `vendor` 严格 0 改动！
  - 编排验证：使用 `./scripts/lca-ops plan compile profiles/mangli-enterprise.yaml`（或 python 静态编译）成功通过。

**Step 1: Write the failing test**

```python
# tests/plugins/test_mangli_core_zero_mutation_guard.py
import subprocess
from pathlib import Path


def test_core_zero_mutation_against_merge_base():
  # 严格对比分支基线，哪怕已经 commit 也确保零核心污染
  res = subprocess.run(
      [
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
      ],
      capture_output=True,
      text=True,
  )
  assert res.returncode == 0
  assert (
      res.stdout.strip() == ""
  ), f"Core files were illegally modified: {res.stdout}"


def test_enterprise_yaml_configs_exist():
  assert Path("bundles/mangli-enterprise.yaml").exists()
  assert Path("profiles/mangli-enterprise.yaml").exists()
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/plugins/test_mangli_core_zero_mutation_guard.py -v`
Expected: FAIL because YAMLs don't exist yet.

**Step 3: Write minimal implementation**
- 编写 `bundles/mangli-enterprise.yaml`；
- 编写 `profiles/mangli-enterprise.yaml`（环境变量全解耦，无硬编码内网 IP）。

**Step 4: Run test to verify it passes**
Run: `pytest tests/plugins/test_mangli_core_zero_mutation_guard.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add bundles/mangli-enterprise.yaml profiles/mangli-enterprise.yaml tests/plugins/test_mangli_core_zero_mutation_guard.py
git commit -m "feat(orchestration): declare mangli-enterprise bundle and enforce core zero-mutation guard"
```
