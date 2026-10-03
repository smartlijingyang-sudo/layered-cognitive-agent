# Connector SSOT Governance & URL Provenance Gate Architecture Design

> **Author**: Antigravity & User Pairing  
> **Date**: 2026-10-03  
> **Topic**: 连接器用户主权隔离（SSOT）、状态驱动交互闭环与 URL 事实血统门禁（UrlProvenanceGate）系统性治理  
> **Autopilot Ladder**: `DRAFT` (AP-05)  
> **Status**: APPROVED by User

---

## 1. 背景与核心问题识别

在近期真实会话执行中（涵盖 `run_7d7f42949fbc` 与 `run_e68917adcf9a` 等），暴露出以下三项系统性缺陷与机制断层：

1. **凭证隔离穿透与新用户脏数据**：
   - 当前系统的连接器存储与 Composio 服务依赖单体文件 `~/.lca/composio/connections.json`，未按运行时 `user_id`（如 `~/.lca/users/{user_id}/connectors/`）严格隔离；
   - 甚至 `ConnectorVault` 内部存在向旧全局文件的隐式 fallback，导致新用户初次进入时错误继承了以往历史连接，破坏了多租户主权与数据纯净度。
2. **缺乏“先查状态再动手”的底层强约束**：
   - 当用户要求操作 Google Drive 或 Gmail 时，Agent 虽加载了 `ext` 命名空间，但未先调用状态查询或连接工具确认连接，而是直接脑补或在未验证状态下贸然操作；
   - 违反了操作手册铁律：“动手前先跑 status 确认连接；连上之后先验证再承诺”。
3. **缺少 URL 事实血统认知硬门禁（模型凭空编造链接）**：
   - 前端已具备完善的 `ConnectorAuthCard` 原生弹窗与轮询卡片体系，但若模型未调用工具，而在思考后直接凭空生成虚假链接（如 `https://app.composio.dev/authorize?mode=composio`），系统此前在认知层缺乏机制拦截，导致假链接直接暴露给用户；
   - 必须在更前面建立防线：**让“编链接”这个动作在认知层根本没有发生的机会**。

---

## 2. 架构负向边界与自治阶梯 (AP-01 & AP-05)

### 2.1 Mandatory Boundaries (AP-01)
* **Owns（本设计负责实现与修改的范围）**：
  1. **用户主权存储模型与全局隔离解耦**：
     - 重构 `lca/infrastructure/connectors/core/vault.py` 与 `lca/infrastructure/integrations/composio/settings/settings.py`，连接器持久化严格收敛至 `~/.lca/users/{user_id}/connectors/connections.json`；
     - 彻底切除向全局单文件的隐式 fallback，新用户默认连接器状态为空集。
  2. **状态驱动与执行窄门硬拦截**：
     - 在操作类工具执行底层实现 `ConnectorPreExecutionGuard`：在调用 `GOOGLEDRIVE_*` / `GMAIL_*` 前强校验 SSOT 文件状态；若未处于 `ACTIVE`，立即 fail-fast 拦截并下发结构化 `[widget:connector_auth?...]` 官方卡片。
  3. **认知层 URL 事实血统门禁 (`UrlProvenanceGate`)**：
     - 在 `lca/cognition/think/gate/` 责任链挂载门禁，静态扫描决策与回复中的外部 URL，必须严格具备 Session 事实血统（工具 Observation / Receipt 或平台白名单），任何未经工具产出的编造 URL 一律判定 `Verdict(rejected, reason="URL_WITHOUT_PROVENANCE")`。
  4. **动身份先报身份透明契约**：
     - 工具 Observation 回执注入 `account_identity`，Prompt 注入透明交代所用账号身份的强制行为规范。
  5. **自动化测试套件**：覆盖 INV-CONN-01 至 INV-CONN-06 全量不变量。

* **Does NOT own（严格禁止修改的负向边界）**：
  1. 严禁改动宿主机系统网络、外部系统凭据或非 LCA 资产（整机运维归属于 `~/everything-library`）；
  2. 严禁修改原生前端 `lobehub-ui/` 源码（所有前端变动必须通过 `deploy/lobehub/patches/` 声明式补丁落地，保持 100% byte-identical 可逆守卫）；
  3. 严禁改变 C1~C14 认知与执行闭集不变量（不走平行事件通道，状态更新仅走 Session 与 Reducer 单写）。

### 2.2 Autopilot Level
* 定级为 **`DRAFT`**。单流渐进式开发，必须经由测试不变量断言验证与 Git 提交核验。

---

## 3. 详细设计与实现机制

### 3.1 SSOT 文件存储与用户主权隔离模型
- **唯一物理真值**：`~/.lca/users/{user_id}/connectors/connections.json`。
- **存储契约**：
  ```python
  class ConnectionRecord(BaseModel):
      identifier: str           # e.g. "google-drive", "gmail", "github"
      status: str               # "ACTIVE" | "PENDING" | "EXPIRED" | "DISCONNECTED"
      label: str                # e.g. "Google Drive"
      account_identity: str     # e.g. "lichao@gmail.com"
      connected_at: str         # ISO timestamp
      updated_at: str         # ISO timestamp
  ```
- **隔离规则**：
  - 新用户初次访问，其对应的目录与文件不存在，`ConnectorVault` 判定为空列表 `[]`，绝不读取其他用户或公共目录的数据；
  - 任何写入使用 `atomic_write_json` 临时文件替换，保证多进程并发读写无损坏。

### 3.2 状态驱动交互闭环（三步状态机）

```mermaid
flowchart TD
    UserQuery["用户指令: '查看我的 Google Drive'"] --> LoadExt["Agent 加载 ext 命名空间"]
    LoadExt --> CheckStatus["调用状态/连接工具: 查询 SSOT 文件"]
    CheckStatus --> SSOT{"读取 user/connectors/connections.json: 是否 ACTIVE?"}
    
    SSOT -->|否 (新用户或未连)| ReturnWidget["工具权威生成 [widget:connector_auth] 并回执"]
    ReturnWidget --> AgentReply["Agent 告知未连接，并如实呈现官方授权卡片"]
    
    SSOT -->|是 (已认证)| ReturnActive["工具回执: ACTIVE + 绑定的账号身份"]
    ReturnActive --> DirectUse["Agent 直接调用 GOOGLEDRIVE_* 操作工具执行业务"]
    
    DirectUse --> PreGuard{"执行层前置守卫: 再验 SSOT 文件状态"}
    PreGuard -->|ACTIVE| ExecuteSuccess["安全执行，返回真实文件数据"]
    PreGuard -->|非 ACTIVE 越权调用| FailFast["底层拦截: 返回未连接 + 强刷授权卡片"]
```

1. **查状态（官方授权流）**：
   - 问到 Google，Agent 自动查 `ext`，调用状态查询；
   - 工具直接读取当前 `user_id` 的 SSOT 文件：
     - 若未认证：工具返回动态 OAuth 会话链接，并通过 `format_connector_auth_widget` 生成 `[widget:connector_auth?appName=Google+Drive&authUrl=...&connectionId=...]`；
     - 若已认证：工具返回 `ACTIVE` 以及绑定的 `account_identity`。
2. **执行窄门前置硬拦截 (`ConnectorPreExecutionGuard`)**：
   - 即使模型产生跳步幻觉直接调用操作类工具，底层执行前置守卫核验 SSOT 文件；
   - 若状态非 `ACTIVE`，直接阻断并返回 `Observation(success=False, error="SERVICE_NOT_CONNECTED", widget=...)`。

### 3.3 URL 事实血统门禁 (`UrlProvenanceGate`)
- 位于 `lca/cognition/think/gate/chain.py` 的认知闸门责任链中。
- **血统核验逻辑**：
  1. 正则扫描决策/输出文本中的所有 `http://` 与 `https://` 链接；
  2. 提取当前 Session 历史中由工具执行产生的事实血统（`session.receipts` 中各 `Observation` 的 `stdout`、`payload.auth_url`、`payload.redirect_url` 等）；
  3. 比对白名单（本地回环地址、已知系统静态文档源）；
  4. **违例判定**：凡不在血统或白名单内的外部 URL，Gate 直接判为 `Verdict(rejected, reason="URL_WITHOUT_PROVENANCE")` 并触发决策修复重思。
- **效果**：编造的假 URL 无法流向传输层，彻底杜绝输出假链接。

### 3.4 身份透明契约 (Identity Accountability)
- 外部生态工具在回执中必须显式暴露 `account_identity`；
- Agent 在执行业务操作前必须自述身份，例如：
  > “正在使用绑定的 Google 账号（`lichao@gmail.com`）执行检索……”
- 满足用户反向审计需求。

---

## 4. 自动化测试不变量矩阵 (AP-02)

| 不变量编号 | 核心断言与守护机制 | 对应测试文件 |
|---|---|---|
| **INV-CONN-01 (SSOT 存储隔离)** | 新用户连接器存储严格绑定 `~/.lca/users/{user_id}/connectors/connections.json`；无文件时严格返回空集合 `[]`；严禁隐式 fallback 继承旧全局文件。 | `tests/connectors/test_user_scoped_vault_isolation.py` |
| **INV-CONN-02 (状态驱动执行窄门)** | SSOT 中非 `ACTIVE` 时，直接调用 `GOOGLEDRIVE_*` / `GMAIL_*` 在执行层被硬拦截，产生 `Observation(success=False, error="SERVICE_NOT_CONNECTED")` 并携带标准卡片插桩语法。 | `tests/connectors/test_connector_pre_execution_guard.py` |
| **INV-CONN-03 (URL 事实血统门禁)** | 提取模型回复/决策中的所有外部 URL；未逐字出现在当前 Run 的 Tool Observation / Receipt 或平台白名单中时，`UrlProvenanceGate` 必须 100% 拦截并返回 `Verdict(rejected, reason="URL_WITHOUT_PROVENANCE")`。 | `tests/cognition/test_url_provenance_gate.py` |
| **INV-CONN-04 (官方卡片渲染闭环)** | 未连接状态下工具输出的 `format_connector_auth_widget` 符合标准语法，LobeHub 前端补丁（`connector_auth_card.py`）能稳定将其挂载为原生弹窗卡片；补丁符合 byte-identical 门禁。 | `tests/deploy/test_connector_auth_card_patch.py` |
| **INV-CONN-05 (动身份先报身份)** | 外部凭证操作工具在 SSOT 为 `ACTIVE` 时执行，其 Observation 回执必须包含合法的 `account_identity` 字段，杜绝匿凭证操作。 | `tests/infrastructure/tools/test_connector_identity_disclosure.py` |
| **INV-CONN-06 (全链路端到端符合性)** | 模拟新用户完整会话流：提问 Google Drive → 自动查 ext → SSOT 未连 → 下发官方卡片（0 编造链接） → 模拟 OAuth 回调写入专属 `connections.json` → 次轮识破已连并带身份直接查询。 | `tests/scenario/test_connector_ssot_governance_e2e.py` |

---

## 5. 迁移与兼容性说明 (COMPAT)
- 尊重既有单用户历史：针对历史 `lca-local-user` 或当前已在 `~/.lca/composio/connections.json` 授权的数据，提供一次性无缝安全迁移脚本或检查，将其提升迁移至真实用户的 `~/.lca/users/{user_id}/connectors/connections.json` 中；
- 迁移后彻底废除全局路径，无跨 PR 遗留后门。
