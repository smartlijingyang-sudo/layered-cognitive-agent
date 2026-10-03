# Connector Capability Intent & Zero URL Model Exposure Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 实现携带能力的外部凭据与授权链接零模型穿透（Capability Reference）与确定性带外卡片挂载机制，彻底消解模型漏抄标签、倾倒裸 URL 与自责幻觉。

**Architecture:** 工具执行生成 OAuth 授权短链后存入凭据保险箱（`ConnectorAuthIntentVault`）并签发短门票（`intent_id`）；工具回执与 LLM Context 绝对不含任何 URL，仅传递 `intent_id`；网关层提供确定性卡片兜底保底挂载；前端 `ConnectorAuthCard` 在用户点击授权时经带外接口（`POST /api/connectors/auth-intents/{id}/resolve`）异步兑换真实 URL 并拉起弹窗。

**Tech Stack:** Python 3.12 (Pydantic, Starlette, pytest), TypeScript / React (Ant Design, LobeHub Patch Engine).

---

### Task 1: 契约模型与凭据暂存服务 (`ConnectorAuthIntent` & `ConnectorAuthIntentVault`)

**Files:**
- Create: `lca/contracts/models/connectors/intent.py`
- Create: `lca/infrastructure/connectors/core/intent_vault.py`
- Test: `tests/connectors/test_auth_intent_vault.py`
- Does NOT own: Transport routes, frontend UI, prompt sections (AP-01)
- Invariants to test: INV-CAP-02 (Intent 具有 300s TTL，多租户 user_id 严格隔离，过期返回失效，单例安全) (AP-02)

**Step 1: Write the failing test**

```python
# tests/connectors/test_auth_intent_vault.py
import time
import pytest
from lca.contracts.models.connectors.intent import ConnectorAuthIntent
from lca.infrastructure.connectors.core.intent_vault import ConnectorAuthIntentVault

def test_intent_lifecycle_and_user_isolation():
    vault = ConnectorAuthIntentVault()
    intent_id = vault.create_intent(
        service="google-drive",
        app_name="Google Drive",
        auth_url="https://connect.composio.dev/link/lk_test123",
        connection_id="conn_abc",
        user_id="user_alice",
        ttl_seconds=1,
    )
    assert intent_id.startswith("cai_")

    # 相同用户成功获取
    intent = vault.resolve_intent(intent_id, user_id="user_alice")
    assert intent is not None
    assert intent.auth_url == "https://connect.composio.dev/link/lk_test123"

    # 跨用户访问被拒绝
    assert vault.resolve_intent(intent_id, user_id="user_bob") is None

    # 超时失效
    time.sleep(1.1)
    assert vault.resolve_intent(intent_id, user_id="user_alice") is None
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest tests/connectors/test_auth_intent_vault.py -v`  
Expected: FAIL with ModuleNotFoundError / ImportError

**Step 3: Write minimal implementation**

- 落地 `lca/contracts/models/connectors/intent.py`（frozen Pydantic 契约）
- 落地 `lca/infrastructure/connectors/core/intent_vault.py`（单例、互斥锁、惰性 TTL 清理、用户隔离）

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/connectors/test_auth_intent_vault.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/contracts/models/connectors/intent.py lca/infrastructure/connectors/core/intent_vault.py tests/connectors/test_auth_intent_vault.py
git commit -m "feat(connectors): add ConnectorAuthIntent model and ConnectorAuthIntentVault (INV-CAP-02)"
```

---

### Task 2: 传输层带外能力解析端点 (`POST /api/connectors/auth-intents/{id}/resolve`)

**Files:**
- Modify: `lca/plugins/transport/webserver/routes_1/routes_composio.py`
- Test: `tests/transport/test_routes_auth_intents.py`
- Does NOT own: LLM prompts, frontend react components (AP-01)
- Invariants to test: INV-CAP-03 (正常解析返回 200 与 URL，过期返回 410，越权或未找到返回 404/403) (AP-02)

**Step 1: Write the failing test**

```python
# tests/transport/test_routes_auth_intents.py
from starlette.testclient import TestClient
from starlette.applications import Starlette
from lca.infrastructure.connectors.core.intent_vault import get_default_intent_vault
from lca.plugins.transport/webserver/routes_1/routes_composio import routes as composio_routes

def test_resolve_auth_intent_endpoint():
    app = Starlette(routes=composio_routes)
    client = TestClient(app)

    vault = get_default_intent_vault()
    intent_id = vault.create_intent(
        service="google-drive",
        app_name="Google Drive",
        auth_url="https://connect.composio.dev/link/lk_test_route",
        connection_id="conn_1",
        user_id="default",
        ttl_seconds=300,
    )

    res = client.post(f"/api/connectors/auth-intents/{intent_id}/resolve", headers={"X-User-ID": "default"})
    assert res.status_code == 200
    data = res.json()
    assert data["auth_url"] == "https://connect.composio.dev/link/lk_test_route"
    assert data["app_name"] == "Google Drive"

    # 不存在的 intent
    res_404 = client.post("/api/connectors/auth-intents/cai_nonexist/resolve", headers={"X-User-ID": "default"})
    assert res_404.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest tests/transport/test_routes_auth_intents.py -v`  
Expected: FAIL with 404 Not Found on the endpoint

**Step 3: Write minimal implementation**

- 在 `routes_composio.py` 注册 `/api/connectors/auth-intents/{intent_id}/resolve` 路由；
- 从请求 Header `X-User-ID` 提取用户身份（默认 fallback 为当前已认证用户）；
- 调用 `vault.resolve_intent(...)`，正确返回 200 / 404 / 410。

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/transport/test_routes_auth_intents.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/plugins/transport/webserver/routes_1/routes_composio.py tests/transport/test_routes_auth_intents.py
git commit -m "feat(transport): add auth-intents resolve endpoint (INV-CAP-03)"
```

---

### Task 3: 工具与适配层彻底消解 URL 暴露 (`composioConnect` 与 `ConnectorPreExecutionGuard`)

**Files:**
- Modify: `lca/infrastructure/tools/composio/__init__.py`
- Modify: `lca/infrastructure/connectors/core/adapter.py`
- Test: `tests/connectors/test_zero_model_url_leakage.py`
- Does NOT own: Frontend react components, host machine ops (AP-01)
- Invariants to test: INV-CAP-01 (工具 Observation 与 Payload 绝对不含 http/https 链接，仅含 intent_id 与 widget 挂载标签) (AP-02)

**Step 1: Write the failing test**

```python
# tests/connectors/test_zero_model_url_leakage.py
import pytest
from lca.infrastructure.tools.composio import ComposioManagementExecutor
from lca.infrastructure.connectors.core.adapter import format_connection_not_active_observation
from lca.infrastructure.connectors.core.exceptions import ConnectionNotActiveError

@pytest.mark.asyncio
async def test_composio_connect_zero_url_leakage(monkeypatch):
    # 模拟 integration.create_connection 返回未连接短链
    ...
    obs = await executor.composioConnect({"service": "google-drive"})
    assert obs.success is True
    # 核心不变量：LLM 看到的 text 与 payload 绝无 http/https 敏感短链
    assert "http://" not in obs.payload["text"]
    assert "https://" not in obs.payload["text"]
    assert "intent_id" in obs.payload
    assert obs.payload["intent_id"].startswith("cai_")
    assert "widget_tag" in obs.payload
    assert "intentId=" in obs.payload["widget_tag"]
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest tests/connectors/test_zero_model_url_leakage.py -v`  
Expected: FAIL because observation currently contains redirect_url

**Step 3: Write minimal implementation**

- `composioConnect`:
  - 接入 `ConnectorAuthIntentVault`，将真实 URL 写入 Vault 并获得 `intent_id`；
  - 彻底切除 text 中的 `{redirect}`；
  - 输出 `[widget:connector_auth?intentId=...&appName=...]`；
  - description 更新为声明交互卡片门票，严禁输出裸 URL；
- `adapter.py`:
  - `format_connection_not_active_observation` 同样使用 `intent_id` 形式格式化卡片。

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/connectors/test_zero_model_url_leakage.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/tools/composio/__init__.py lca/infrastructure/connectors/core/adapter.py tests/connectors/test_zero_model_url_leakage.py
git commit -m "feat(connectors): enforce zero model url exposure in tools and adapter (INV-CAP-01)"
```

---

### Task 4: 网关层确定性卡片兜底保底挂载 (`routes_runs_sessions.py` / Finalizer)

**Files:**
- Modify: `lca/runtime/session/run_session_writer.py` (或消息组装投递点)
- Test: `tests/runtime/test_gateway_intent_widget_fallback.py`
- Does NOT own: Frontend UI, host ops (AP-01)
- Invariants to test: INV-CAP-04 (模型输出纯文本或漏掉 widget 标签时，网关确保前端收到的消息 100% 携带该步骤的 widget 挂载标签) (AP-02)

**Step 1: Write the failing test**

```python
# tests/runtime/test_gateway_intent_widget_fallback.py
def test_gateway_appends_widget_when_model_omits():
    # 模拟模型输出纯文本："已为你发起连接，请点击卡片完成授权。"（未携带 [widget:...] 标签）
    # 但该轮次产生了 intent_id = "cai_test123", app_name = "Google Drive"
    final_content = ensure_intent_widget_in_assistant_message(
        raw_model_content="已为你发起连接，请点击卡片完成授权。",
        pending_intents=[{"intent_id": "cai_test123", "app_name": "Google Drive"}],
    )
    assert "[widget:connector_auth?intentId=cai_test123&appName=Google+Drive]" in final_content
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest tests/runtime/test_gateway_intent_widget_fallback.py -v`  
Expected: FAIL with function missing

**Step 3: Write minimal implementation**

- 落地 `ensure_intent_widget_in_assistant_message` 并挂载至消息投递/持久化切面；
- 避免重复追加：若 `raw_model_content` 中已包含该 `intentId`，则不重复追加。

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/runtime/test_gateway_intent_widget_fallback.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/runtime/session/run_session_writer.py tests/runtime/test_gateway_intent_widget_fallback.py
git commit -m "feat(runtime): add gateway deterministic widget fallback guard (INV-CAP-04)"
```

---

### Task 5: 前端补丁升级 (`ConnectorAuthCard.tsx` 与 `connector_auth_card.py`)

**Files:**
- Modify: `deploy/lobehub/patches/ui/ConnectorAuthCard.tsx`
- Modify: `deploy/lobehub/patches/ui/connector_auth_card.py`
- Test: `tests/deploy/test_connector_auth_card_patch.py`
- Does NOT own: python contracts/infrastructure (AP-01)
- Invariants to test: INV-CAP-05 (ConnectorAuthCard 支持 intentId 异步兑换，前端补丁 100% byte-identical) (AP-02)

**Step 1: Write the failing test**

```python
# tests/deploy/test_connector_auth_card_patch.py (新增测试用例)
def test_connector_auth_card_intent_id_support():
    path = _get_card_tsx_path()
    content = path.read_text(encoding="utf-8")
    assert "intentId" in content
    assert "/api/connectors/auth-intents/" in content
    assert "resolve" in content
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest tests/deploy/test_connector_auth_card_patch.py -k test_connector_auth_card_intent_id_support -v`  
Expected: FAIL with assertion error

**Step 3: Write minimal implementation**

- `ConnectorAuthCard.tsx`:
  - 增加 `intentId?: string` 属性；
  - 在 `handleAuthorize` 中，若有 `intentId`，先 POST `/api/connectors/auth-intents/${intentId}/resolve` 获取真实短链，再调用 `window.open`；
  - 兼容原有 `authUrl`；
- `connector_auth_card.py`:
  - 匹配 `[widget:connector_auth?intentId=...]`，解析出 `intentId` 并透传给组件；
  - 清理正文中的裸 `composio.dev` 链接和 widget 标签。
- 运行 `python3 deploy/lobehub/patch_lobehub.py connector_auth_card` 重新应用补丁。

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/deploy/test_connector_auth_card_patch.py -v`  
Expected: PASS (all 6 tests pass)

**Step 5: Commit**

```bash
git add deploy/lobehub/patches/ui/ConnectorAuthCard.tsx deploy/lobehub/patches/ui/connector_auth_card.py tests/deploy/test_connector_auth_card_patch.py
git commit -m "feat(ui): upgrade ConnectorAuthCard to resolve capability intents asynchronously (INV-CAP-05)"
```

---

### Task 6: ADR-0280 沉淀与全链路端到端集成验收

**Files:**
- Create: `docs/adr/0280-zero-model-exposure-for-capable-urls.md`
- Modify: `docs/adr/README.md`
- Test: `tests/scenario/test_connector_capability_intent_e2e.py`
- Does NOT own: External non-LCA machine ops (AP-01)
- Invariants to test: INV-CAP-01 ~ INV-CAP-06 全量闭环 (AP-02)

**Step 1: Write the failing test**

```python
# tests/scenario/test_connector_capability_intent_e2e.py
@pytest.mark.asyncio
async def test_connector_capability_intent_full_flow():
    # 模拟完整端到端：
    # 1. 触发连接工具 -> 产生 intent_id (断言零 URL 泄漏)
    # 2. 模拟模型输出普通文本 -> 断言网关确定性补齐 widget 挂载
    # 3. 前端调用 resolve 接口 -> 断言获取真实短链
    # 4. 模拟短链过期 -> 断言 resolve 返回 410
    ...
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest tests/scenario/test_connector_capability_intent_e2e.py -v`  
Expected: FAIL

**Step 3: Write minimal implementation**

- 补齐集成场景测试套件；
- 编写 `docs/adr/0280-zero-model-exposure-for-capable-urls.md` 并在 `docs/adr/README.md` 注册；
- 校验 `ruff check` 与 `git diff --check`。

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/scenario/test_connector_capability_intent_e2e.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add docs/adr/0280-zero-model-exposure-for-capable-urls.md docs/adr/README.md tests/scenario/test_connector_capability_intent_e2e.py
git commit -m "docs(adr): add ADR-0280 and verify connector capability intent e2e (INV-CAP-06)"
```
