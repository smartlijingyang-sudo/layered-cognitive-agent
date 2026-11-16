# 企业级应用集成与统一接口封装实施计划 (Mangli Enterprise Integration Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于 LCA 插件化微内核，在零修改底层核心代码的前提下，构建企业统一鉴权中间件（AES-ECB-PKCS5Padding + 权限缓存）、收敛的 REST+SSE 接口（项目/会话/流式/文件/取消/模型）、5 大企业数据工具集（问数A2A/OA MCP/Wiki/知识库/沙箱文件）以及一个开箱即用的轻量单页测试控制台（Playground）。

**Architecture:** 纯外围插件扩展（Seam/Provider 范式）配合声明式 YAML 编排。通过 Starlette 网关动态注册路由与中间件，通过 `tools` Seam 动态注入能力，全链路事件由追加式 Session 日志流（`*.spine.jsonl`）保证只读与确定性。

**Tech Stack:** Python 3.12, Starlette, Pydantic, Cryptography (AES-ECB-PKCS7), HTTPX (Async A2A/Permissions), Server-Sent Events (SSE), HTML5/Tailwind/Vanilla JS.

---

### Task 1: Mangli 鉴权与用户上下文模块 (AES 解密 + 权限补全)

**Files:**
- Create: `lca/plugins/transport/webserver/handlers/auth/mangli_auth.py`
- Test: `tests/plugins/transport/test_mangli_auth.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca_kernel/`, `vendor/` (AP-01)
- Invariants to test:
  - INV-01: Java `AES/ECB/PKCS5Padding` + Hex 编解码双向对齐，SHA1PRNG 密钥推导与纯 Hex 密钥兼容。
  - INV-02: 权限微服务调用异步处理，内存 LRU Cache 5 分钟 TTL 命中与过期刷新，错误降级与异常隔离。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_mangli_auth.py
import pytest
from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
    MangliAuthService,
    MangliUserContext,
    decrypt_mangli_user_header,
    derive_sha1prng_key,
)


def test_sha1prng_key_derivation():
  password = b"company_secret_2026"
  key = derive_sha1prng_key(password)
  assert len(key) == 16


def test_aes_ecb_pkcs5_decrypt_roundtrip():
  # 测试 Java 端 Hex 编码 + AES/ECB/PKCS5Padding 解密
  key = derive_sha1prng_key(b"test_pwd")
  sample_json = (
      '{"user_id":"U1001","name":"李四","title":"架构师","dept_id":"D01","dept_name":"技术部"}'
  )
  from lca.plugins.transport.webserver.handlers.auth.mangli_auth import (
      encrypt_mangli_user_header_for_test,
  )

  hex_encrypted = encrypt_mangli_user_header_for_test(sample_json, key)
  decrypted = decrypt_mangli_user_header(hex_encrypted, key)
  assert decrypted["user_id"] == "U1001"
  assert decrypted["name"] == "李四"


@pytest.mark.asyncio
async def test_permission_cache_ttl(monkeypatch):
  call_count = 0

  async def mock_fetch_permissions(ticket: str, user_id: str):
    nonlocal call_count
    call_count += 1
    return ["user:read", "project:access"], ["engineer"]

  service = MangliAuthService(fetch_fn=mock_fetch_permissions)
  # 第一次调用：未命中缓存
  perms, roles = await service.get_permissions("ticket_123", "U1001")
  assert call_count == 1
  assert "user:read" in perms

  # 第二次调用：命中 5min 缓存，不增加网络调用
  perms2, roles2 = await service.get_permissions("ticket_123", "U1001")
  assert call_count == 1
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/plugins/transport/test_mangli_auth.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`.

**Step 3: Write minimal implementation**
实现 `lca/plugins/transport/webserver/handlers/auth/mangli_auth.py`：
- `derive_sha1prng_key(password: bytes) -> bytes`
- `decrypt_mangli_user_header(hex_str: str, key: bytes) -> dict`
- `MangliUserContext` (Pydantic model)
- `MangliAuthService` 带 TTL 缓存的异步权限获取与 ContextVar 管理

**Step 4: Run test to verify it passes**
Run: `pytest tests/plugins/transport/test_mangli_auth.py -v`
Expected: PASS (3/3 passed).

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/handlers/auth/mangli_auth.py tests/plugins/transport/test_mangli_auth.py
git commit -m "feat(auth): implement Mangli AES-ECB-PKCS5Padding decrypt and permission cache"
```

---

### Task 2: 企业统一 REST + SSE 路由插件 (`routes_mangli_api.py`)

**Files:**
- Create: `lca/plugins/transport/webserver/routes_mangli_api.py`
- Test: `tests/plugins/transport/test_routes_mangli_api.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca_kernel/` (AP-01)
- Invariants to test:
  - INV-03: 项目隔离与游离会话（`project_id is None`）访问控制边界。
  - INV-04: SSE 6 类事件流式契约闭环（`text_delta`, `tool_start`, `tool_end`, `file_created`, `done`, `error`）及 15 秒心跳包（`: ping\n\n`）。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_routes_mangli_api.py
import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette


def test_mangli_routes_registration():
  # 测试插件在 route_registry 中正确注册所有 /api/v1/* 路由
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
  assert "/api/v1/files" in paths
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/plugins/transport/test_routes_mangli_api.py -v`
Expected: FAIL with `ModuleNotFoundError`.

**Step 3: Write minimal implementation**
实现 `lca/plugins/transport/webserver/routes_mangli_api.py`：
- 使用 `@plugin(id="mangli-enterprise-routes", requires=("route_registry",))` 装饰；
- 封装项目 CRUD、会话列表/创建（支持游离会话）、发起运行、取消任务代理、模型列表代理；
- 封装带有 15 秒心跳的 `GET /api/v1/runs/{run_id}/stream` SSE 流式输出处理器。

**Step 4: Run test to verify it passes**
Run: `pytest tests/plugins/transport/test_routes_mangli_api.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/routes_mangli_api.py tests/plugins/transport/test_routes_mangli_api.py
git commit -m "feat(routes): implement Mangli enterprise REST and SSE streaming routes"
```

---

### Task 3: 5 大企业数据与能力工具插件 (`mangli_enterprise_tools.py`)

**Files:**
- Create: `lca/plugins/tools/mangli_enterprise_tools.py`
- Test: `tests/plugins/tools/test_mangli_enterprise_tools.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca_kernel/` (AP-01)
- Invariants to test:
  - INV-05: 5 大工具入参强类型契约校验；上下文透传（自动带入当前调用者 `user_id` 与 `dept_id`）；文件安全沙箱读写回执闭环。

**Step 1: Write the failing test**

```python
# tests/plugins/tools/test_mangli_enterprise_tools.py
import pytest
from lca.plugins.tools.mangli_enterprise_tools import (
    QueryDataAgentTool,
    SearchWikiTool,
    SearchKnowledgeBaseTool,
    WorkspaceFileOpsTool,
)


def test_tools_schema_and_metadata():
  tool = QueryDataAgentTool()
  assert tool.name == "query_data_agent"
  assert "query" in tool.parameters_schema["properties"]

  kb_tool = SearchKnowledgeBaseTool()
  assert kb_tool.name == "search_knowledge_base"


@pytest.mark.asyncio
async def test_file_ops_isolation_in_sandbox(tmp_path):
  tool = WorkspaceFileOpsTool(root_dir=tmp_path)
  # 写入文件
  receipt = await tool.write_file(
      filename="test_report.md",
      content="# 销售汇总\n金额: 1000",
      project_id="proj_01",
      session_id="sess_01",
  )
  assert receipt["file_id"] is not None
  # 读取文件
  read_content = await tool.read_file(
      receipt["file_id"], project_id="proj_01", session_id="sess_01"
  )
  assert "销售汇总" in read_content
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/plugins/tools/test_mangli_enterprise_tools.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
实现 `lca/plugins/tools/mangli_enterprise_tools.py`：
- `QueryDataAgentTool` (HTTP A2A 委托)
- `SearchWikiTool` & `SearchJiraTool` (REST 工具)
- `SearchKnowledgeBaseTool` (企业知识库检索)
- `WorkspaceFileOpsTool` (受控工作区安全读写)
- `@plugin(id="mangli-enterprise-tools", requires=("tools",))` 工厂注册入口

**Step 4: Run test to verify it passes**
Run: `pytest tests/plugins/tools/test_mangli_enterprise_tools.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/plugins/tools/mangli_enterprise_tools.py tests/plugins/tools/test_mangli_enterprise_tools.py
git commit -m "feat(tools): implement 5 Mangli enterprise data and workspace tools"
```

---

### Task 4: 声明式编排配置与核心零修改验证

**Files:**
- Create: `bundles/mangli-enterprise.yaml`
- Create: `profiles/mangli-enterprise.yaml`
- Test: `tests/plugins/test_mangli_enterprise_bundle_invariants.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca_kernel/` (AP-01)
- Invariants to test:
  - INV-06: 核心零修改门禁（`git diff lca/contracts lca/cognition lca/runtime lca/loop lca/framework lca_kernel` 必为空）；
  - `CompiledRunPlan` 解析与图验证通过。

**Step 1: Write the failing test**

```python
# tests/plugins/test_mangli_enterprise_bundle_invariants.py
import subprocess
from pathlib import Path


def test_core_zero_mutation_guard():
  # 严格验证核心目录零代码改动
  res = subprocess.run(
      [
          "git",
          "diff",
          "--name-only",
          "lca/contracts",
          "lca/cognition",
          "lca/runtime",
          "lca/loop",
          "lca/framework",
          "lca_kernel",
      ],
      capture_output=True,
      text=True,
  )
  assert res.returncode == 0
  assert res.stdout.strip() == "", (
      f"Core files were illegally modified: {res.stdout}"
  )


def test_enterprise_profile_exists():
  assert Path("bundles/mangli-enterprise.yaml").exists()
  assert Path("profiles/mangli-enterprise.yaml").exists()
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/plugins/test_mangli_enterprise_bundle_invariants.py -v`
Expected: FAIL because yaml files do not exist yet.

**Step 3: Write minimal implementation**
编写：
- `bundles/mangli-enterprise.yaml`
- `profiles/mangli-enterprise.yaml`

**Step 4: Run test to verify it passes**
Run: `pytest tests/plugins/test_mangli_enterprise_bundle_invariants.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add bundles/mangli-enterprise.yaml profiles/mangli-enterprise.yaml tests/plugins/test_mangli_enterprise_bundle_invariants.py
git commit -m "feat(profile): add mangli-enterprise bundle and profile orchestration"
```

---

### Task 5: 极简单页验证控制台 (Playground UI)

**Files:**
- Create: `lca/infrastructure/web/static/mangli_playground.html`
- Modify: `lca/plugins/transport/webserver/routes_mangli_api.py` (挂载 `GET /playground` 路由)
- Test: `tests/plugins/transport/test_playground_endpoint.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca_kernel/` (AP-01)
- Invariants to test:
  - 访问 `GET /playground` 返回 200 与 HTML 页面，页面包含完整的身份输入、项目会话树、打字机流式渲染与文件下载功能。

**Step 1: Write the failing test**

```python
# tests/plugins/transport/test_playground_endpoint.py
from pathlib import Path


def test_playground_file_exists():
  p = Path("lca/infrastructure/web/static/mangli_playground.html")
  assert p.exists()
  content = p.read_text(encoding="utf-8")
  assert "EventSource" in content or "fetch" in content  # 包含流式接收
  assert "X-Mangli-User" in content  # 包含 Header 模拟输入
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/plugins/transport/test_playground_endpoint.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 编写免构建打包的标准单页 `mangli_playground.html`（现代化 UI，包含身份模拟输入框、会话列表、打字机流式窗口、折叠工具卡片、终止按钮与文件列表）；
- 在 `routes_mangli_api.py` 中注册 `GET /playground` 返回该静态页面。

**Step 4: Run test to verify it passes**
Run: `pytest tests/plugins/transport/test_playground_endpoint.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/infrastructure/web/static/mangli_playground.html lca/plugins/transport/webserver/routes_mangli_api.py tests/plugins/transport/test_playground_endpoint.py
git commit -m "feat(ui): add standalone single-page verification playground"
```
