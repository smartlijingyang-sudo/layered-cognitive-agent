# Connector SSOT Governance & URL Provenance Gate Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 彻底落实连接器用户主权隔离（SSOT）、状态驱动执行窄门拦截（Pre-Execution Guard）与 URL 事实血统认知门禁（UrlProvenanceGate），让 Agent 针对外部生态实现“自动查 ext → 查连接状态 → 未连给卡片 / 连了直接用”，机制上杜绝虚假链接与跨用户凭据污染。

**Architecture:** 
1. 存储层：以 `~/.lca/users/{user_id}/connectors/connections.json` 为唯一真值（SSOT），彻底清除全局单文件 fallback，保障新用户 100% 干净隔离；
2. 认知层：在 Think Gate 责任链挂载 `UrlProvenanceGate`，严厉拦截无 Session 事实血统的捏造链接；Prompt 管道装配 `ConnectedServicesSection`；
3. 执行层：构建 `ConnectorPreExecutionGuard`，在调用外部操作前强核验 SSOT 文件状态，未激活直接 fail-fast 拦截并下发官方动态卡片；工具回执注入 `account_identity` 规范身份透明。

**Tech Stack:** Python 3.10+, Pydantic v2, pytest, LCA Think Gate Chain, Composio Tool Provider, LobeHub UI Patch.

---

### Task 1: 用户主权 SSOT 存储与全局隔离解耦 (INV-CONN-01)

**Files:**
- Modify: `lca/infrastructure/connectors/core/vault.py`
- Modify: `lca/infrastructure/integrations/composio/settings/settings.py`
- Modify: `lca/infrastructure/integrations/composio/service/service.py`
- Test: `tests/connectors/test_user_scoped_vault_isolation.py`
- Does NOT own: `deploy/lobehub/**`, `lca/cognition/**` (AP-01)
- Invariants to test: INV-CONN-01（用户级隔离、无文件返回空集、绝不读取全局 `composio/connections.json` 脏数据）

**Step 1: Write the failing test**
编写 `tests/connectors/test_user_scoped_vault_isolation.py`：
- 断言任意新用户 `new-user-123` 初始调用 `ConnectorVault(user_id="new-user-123").list_connections()` 严格返回 `[]`，即使全局 `composio/connections.json` 存在脏数据；
- 断言 `ComposioSettings.from_plugin_config` 或 `ComposioIntegration` 能根据 `user_id` 解析出其专属路径；
- 断言保存连接时写入的是 `~/.lca/users/{user_id}/connectors/connections.json`。

**Step 2: Run test to verify it fails**
Run: `pytest tests/connectors/test_user_scoped_vault_isolation.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 在 `vault.py` 中移除 `_get_composio_connections_file` fallback，仅读取 `self._get_user_connections_file()`；
- 在 `settings.py` 与 `service.py` 中支持基于 `user_id` 动态计算 `connections_path`，确保多用户各自独立维护 `connections.json`。

**Step 4: Run test to verify it passes**
Run: `pytest tests/connectors/test_user_scoped_vault_isolation.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add lca/infrastructure/connectors/core/vault.py lca/infrastructure/integrations/composio/ tests/connectors/test_user_scoped_vault_isolation.py
git commit -m "feat(connectors): enforce user-scoped SSOT vault isolation without global fallback"
```

---

### Task 2: 认知层 Auth 意图 URL 事实血统门禁 `AuthUrlProvenanceGate` (INV-CONN-03)

**Files:**
- Create: `lca/cognition/think/gate/url_provenance.py`
- Modify: `lca/cognition/think/gate/chain.py`
- Test: `tests/cognition/test_url_provenance_gate.py`
- Does NOT own: `lca/infrastructure/tools/**`, `deploy/lobehub/**` (AP-01)
- Invariants to test: INV-CONN-03（精准收窄至 Auth 意图 URL，无事实血统必须 100% 驳回为 `URL_WITHOUT_PROVENANCE`；放行普通文档链接、repo 地址与用户复述）

**Step 1: Write the failing test**
编写 `tests/cognition/test_url_provenance_gate.py`：
- 测试当回复包含未经工具背书的 Auth 链接（如 `https://app.composio.dev/authorize?mode=composio` 或包含 `oauth`/`token` 路径）时，Gate 严格驳回；
- 测试正常文档 URL、GitHub 仓库链接、本地 localhost 链接，以及用户在会话中主动粘贴并由模型引用的链接，Gate 正常放行；
- 测试经过工具 Observation 真实返回的官方授权链接，Gate 正常放行。

**Step 2: Run test to verify it fails**
Run: `pytest tests/cognition/test_url_provenance_gate.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 编写 `AuthUrlProvenanceGate`，利用 Auth 意图识别正则过滤出需要强核验的认证授权类 URL；
- 核验 Session 事实流；
- 在 `chain.py` 挂载门禁。

**Step 4: Run test to verify it passes**
Run: `pytest tests/cognition/test_url_provenance_gate.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add lca/cognition/think/gate/url_provenance.py lca/cognition/think/gate/chain.py tests/cognition/test_url_provenance_gate.py
git commit -m "feat(cognition): add AuthUrlProvenanceGate scoped to authorization URLs"
```

---

### Task 3: 状态驱动执行窄门硬拦截 `ConnectorPreExecutionGuard` (INV-CONN-02)

**Files:**
- Create: `lca/infrastructure/connectors/core/guard.py`
- Modify: `lca/infrastructure/tools/composio/__init__.py`
- Test: `tests/connectors/test_connector_pre_execution_guard.py`
- Does NOT own: `lca/cognition/**`, `deploy/lobehub/patches/ui/**` (AP-01)
- Invariants to test: INV-CONN-02（分层解耦：执行层拦截抛出类型化 `ConnectionNotActiveError`；适配层转译结构化回执，严禁执行层感知前端卡片语法）

**Step 1: Write the failing test**
编写 `tests/connectors/test_connector_pre_execution_guard.py`：
- 执行层断言：未激活服务直接调用操作类工具（如 `GOOGLEDRIVE_FIND_FILE`、`GMAIL_SEND_EMAIL`），Guard 抛出 `ConnectionNotActiveError(service=..., user_id=...)`；
- 适配层断言：工具执行封装器捕获该异常，向外输出包含错误类型与服务标识的结构化回执；
- 验证已激活状态放行。

**Step 2: Run test to verify it fails**
Run: `pytest tests/connectors/test_connector_pre_execution_guard.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 落地 `ConnectionNotActiveError` 契约与 `ConnectorPreExecutionGuard`；
- 在 Composio Tool Provider 中装配分层拦截与适配转译。

**Step 4: Run test to verify it passes**
Run: `pytest tests/connectors/test_connector_pre_execution_guard.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add lca/infrastructure/connectors/core/guard.py lca/infrastructure/tools/composio/__init__.py tests/connectors/test_connector_pre_execution_guard.py
git commit -m "feat(connectors): add ConnectorPreExecutionGuard with layered ConnectionNotActiveError"
```

---

### Task 4: 根除走文本偷懒病根 & 动身份先报身份透明契约 (INV-CONN-05)

**Files:**
- Modify: `lca/plugins/prompts/sections/connected_services.py`
- Modify: `lca/plugins/prompts/sections/text.py`
- Modify: `lca/plugins/prompts/sections/plugin.py`
- Modify: `lca/plugins/prompts/template_provider.py`
- Modify: `lca/infrastructure/tools/composio/__init__.py`
- Test: `tests/infrastructure/tools/test_connector_identity_disclosure.py`
- Does NOT own: `lca/contracts/models/**` (AP-01)
- Invariants to test: INV-CONN-05（Prompt 核心铁律注入、工具回执显式包含 `account_identity`）

**Step 1: Write the failing test**
编写 `tests/infrastructure/tools/test_connector_identity_disclosure.py`：
- 断言 System Prompt 包含核心铁律：禁止在文本中拼装动态授权/OAuth/连接 URL，所有授权与连接动作必须调用官方工具生成；
- 断言调用操作类工具时，回执 payload 包含非空 `account_identity`；
- 断言 Prompt 模板成功装配 `ConnectedServicesSection`。

**Step 2: Run test to verify it fails**
Run: `pytest tests/infrastructure/tools/test_connector_identity_disclosure.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 在 `composio/__init__.py` 中补全回执中的 `account_identity`；
- 在 `plugin.py` 与 `template_provider.py` 中正式挂载 `connected_services` 段。

**Step 4: Run test to verify it passes**
Run: `pytest tests/infrastructure/tools/test_connector_identity_disclosure.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add lca/infrastructure/tools/composio/__init__.py lca/plugins/prompts/ tests/infrastructure/tools/test_connector_identity_disclosure.py
git commit -m "feat(connectors): wire ConnectedServicesSection and identity disclosure contract"
```

---

### Task 5: 全链路端到端集成验收与 Pre-Push 门禁体检 (INV-CONN-01 ~ 06)

**Files:**
- Create: `tests/scenario/test_connector_ssot_governance_e2e.py`
- Test: 全量关联套件
- Invariants to test: INV-CONN-01 至 INV-CONN-06

**Step 1: Write E2E integration test**
编写 `tests/scenario/test_connector_ssot_governance_e2e.py`：
- 端到端贯通全流程：提问 Google Drive → 查 ext → 查 status 发现未连 → 输出官方卡片（0 编造链接） → 模拟 OAuth 回调写入专属 `connections.json` → 次轮识破已连接并携带账号身份直接执行文件查询。

**Step 2: Run E2E test**
Run: `pytest tests/scenario/test_connector_ssot_governance_e2e.py -v`
Expected: PASS

**Step 3: Run comprehensive verification**
```bash
pytest tests/connectors/ tests/cognition/test_url_provenance_gate.py tests/infrastructure/tools/test_connector_identity_disclosure.py tests/scenario/test_connector_ssot_governance_e2e.py -v
ruff check lca/ tests/
ruff format --check lca/ tests/
git diff --check
```
Expected: ALL PASS, 0 errors, 0 warnings.

**Step 4: Commit**
```bash
git add tests/scenario/test_connector_ssot_governance_e2e.py
git commit -m "test(connectors): add end-to-end conformance test for connector SSOT governance"
```
