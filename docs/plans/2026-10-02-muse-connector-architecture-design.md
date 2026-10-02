# 工业级 7 层连接器架构设计规范 (Muse Connector Architecture Design)

- **创建日期**: 2026-10-02
- **状态**: Approved (用户已逐节完成确认)
- **作者**: Antigravity & User

---

## 1. 背景与问题定义

### 1.1 历史缺陷与根因追溯
在前期真实会话（如 `run_1aed82f56d32`）中，用户在抽屉或设置中连接了 GitHub、Gmail 和 Google Drive 后，对话中询问 Agent 相关仓库信息，Agent 却回应“不知道自己已连接 GitHub”。
经深度复盘排查，查明三大根因：
1. **工具元数据膨胀与溢出截断（Tool Metadata Spill）**：
   - 挂载了 823 个 GitHub 工具 + 51 个 Drive 工具 + 23 个 Gmail 工具（总计近 900 工具）；
   - 在 `tool_search(namespace='ext')` 返回时，消息内容超出了 2000 字符限制，触发系统保护强制截断 `...[spilled]`，截断点恰好把全部 `GITHUB_*` 工具切除。
2. **缺乏 Prompt 先验认知注入（Prompt vs Tool Injection Gap）**：
   - Tool 注入（`tools: [...]`）仅解决“如何调用结构化参数”，而未在认知层解决“我知道自己拥有什么能力”；
   - System Prompt 中缺乏已连接服务状态段（`ConnectedServicesSection`），导致模型在未调用工具前缺乏先验信念。
3. **缺乏连接器运行时（Connector Runtime 缺位）**：
   - 之前仅将第三方 API 当作普通 Tool 裸挂，身后缺乏状态机、安全凭证沙箱、权限层和配额器的护卫。

### 1.2 数据存储归属与用户隔离模型 (File as SSOT)
- **LobeHub PostgreSQL 数据库**：仅存储 LobeChat 前端聊天记录与用户基础账号，不作为外部连接器 OAuth 凭证的真值源。
- **LCA 本地用户域 (`~/.lca/users/<user_id>/`)**：
  - `connectors/connections.json`：存储该用户的连接器元数据真值；
  - `connectors/permissions.json`：存储该用户对各连接器 Action 的细粒度权限配置（Allow / Ask / Deny）；
  - `assistants.json`：正向索引管理该用户所属的全部助理。
- **LCA 助理自治域 (`~/.lca/assistants/<asst_id>/`)**：
  - `manifest.json`：反向指针严格回填 `owner_user_id`；
  - `connectors.json`：声明该助理启用的连接器白名单与特定账号绑定。

---

## 2. 系统边界、自治等级与拓扑架构

### 2.1 边界声明 (AP-01 负向边界)
- **Owns (本架构负责)**：
  - 连接器完整运行时（状态机、滑动窗口硬配额、双层正交权限拦截器）；
  - 本地 CLI 命令封装、`manifest.yaml` 规范与自动化 `SKILL.md` 注入；
  - 会话流中与 LobeHub `ConnectorAuthCard` 交互卡片协议的闭环；
  - 启动阶段轻量级 `ConnectedServicesSection` 提示词感知注入。
- **Does NOT Own (本架构严禁侵入)**：
  - 认知主循环（`lca/cognition/` 核心五阶段状态机保持不可变）；
  - LobeHub 官方源码仓库（仅允许在 `deploy/lobehub/patches/` 声明式补丁中协同）；
  - 宿主机系统级运维、网络基础设施或 `~/everything-library` 外部资产。

### 2.2 自治阶梯与四大守卫拓扑
本架构处于 **DRAFT / STAGED 阶段**（首个垂直切片落地 Gmail，随后扩展至 GitHub 和 Google Drive）。
所有连接器调用背后，均由四大守卫守卫：
```
Agent 认知决策 (Think) 
      │
      ▼
[1. 状态机守卫] ──(未连接)──> 唤起 LobeHub ConnectorAuthCard 卡片 ──> 挂起等待
      │ (已连接)
      ▼
[2. 权限层守卫] ──(Scope缺失)──> 增量提权卡片
      │ (Scope满足)
      ├──(Action DENY)──> 直接拒绝 (ActionPermissionDenied)
      ├──(Action ASK)───> 唤起 LobeHub 审批卡片 (等待用户确认)
      │ (Action ALLOW)
      ▼
[3. 配额器守卫] ──(超限)──> 结构化阻断并返回 retry_after_seconds
      │ (在窗口内)
      ▼
[4. 凭证库与隔离执行器] ──(安全管道注入 Token)──> 独立 CLI 进程执行 ──> 返回 Effect Receipt
```

---

## 3. 连接状态机与 LobeHub 交互卡片协议

### 3.1 状态机流转
- `NOT_CONFIGURED`: 缺失 Manifest 或未配置环境；
- `NOT_CONNECTED`: 插件已挂载但无活动 Token；
- `AWAITING_AUTH`: 正在等待用户在 `ConnectorAuthCard` 弹窗完成授权与轮询刷新；
- `ACTIVE`: 凭据可用，可正常派发 API 命令；
- `ADDITIONAL_ACCESS`: 当前 Scope 无法满足高危调用，触发增量提权卡片；
- `TOKEN_EXPIRED`: 远端 Token 失效，自愈退回 `AWAITING_AUTH`；
- `RATE_LIMITED`: 触发配额硬上限，短暂休眠退避。

### 3.2 LobeHub `ConnectorAuthCard` 交互闭环契约
1. **守卫判定与 CLI 拦截**：
   - CLI Pre-flight 检查发现处于 `NOT_CONNECTED` 时，返回结构化 JSON：
     ```json
     {
       "status": "not_connected",
       "appName": "Gmail",
       "connectionId": "ca_gmail_123",
       "authUrl": "https://backend.composio.dev/api/v1/auth/redirect?token=..."
     }
     ```
2. **Prompt 契约**：
   - 规定 Agent 遇到 `not_connected` 时，**严禁输出裸露链接或让用户去设置里找**；
   - 必须单独输出标准卡片插桩语法：
     ```text
     [widget:connector_auth?appName=Gmail&authUrl=<authUrl>&connectionId=<connectionId>]
     ```
3. **LobeHub 前端渲染 (`ConnectorAuthCard.tsx`)**：
   - 正则自动拦截擦除该标记，无缝挂载交互式卡片；
   - 用户点击「立即授权连接」唤起 620×720 独立弹窗；
   - 前端以 2.5s 间隔向 `/lca-api/composio/connections/${connectionId}/refresh` 轮询；
   - 成功后卡片自动切换为 `🟢 已连接` 并回调会话，无需用户刷新页面。

### 3.3 多账号体系 (Multi-Account)
- `gmail accounts`: 列出当前可用的账号列表及状态；
- `gmail +send --account <id>`: 显式切换账号路由；
- `gmail connect --add-account`: 返回 `add_account_url`，通过卡片绑定第二个账号；
- `gmail disconnect --account <id>`: 安全注销并清空该账号本地凭证。

---

## 4. 双层正交权限模型与滑动窗口硬配额

### 4.1 双层正交权限
- **第一层：Provider 远端 Scope**（粗粒度底层通行证）；
- **第二层：LCA 本地 Action 规则**（细粒度业务开关）：
  - 存储于 `~/.lca/users/<user_id>/connectors/permissions.json`；
  - `ALLOW`: 直接放行（如搜索、查阅）；
  - `ASK`: 敏感写操作，拦截并唤起 LobeHub 审批卡片（如 `+send` 发邮件、提 PR）；
  - `DENY`: 彻底禁用该操作；
  - **即时生效**：更改权限设置无需重新 OAuth 认证。

### 4.2 写操作双保险安全红线 (Two-Phase Write)
1. **Token 永不进 Agent 提示词、上下文、日志或文件**；
2. **写操作两阶段文件暂存（`--upload` 机制）**：
   - 发送长内容/代码修改时，Agent 必须先将草稿写入本地临时文件；
   - 审批卡片直接渲染该暂存文件的 Diff 或 HTML 预览；
   - 经用户批准后，CLI 从暂存文件读取正文提交给外部 API，杜绝命令行字符注入与篡改。

### 4.3 滑动窗口硬配额执行器
- `manifest.yaml` 中声明 `units_per_minute` 与各 API 的 `method_units` 成本权重；
- 执行器实时统计 60 秒内消费总额；超限即时阻断并返回：
  ```json
  {
    "error": "connector_rate_limited",
    "retry_after_seconds": 25,
    "message": "Quota exceeded. Please retry after 25s."
  }
  ```
- 在 `SKILL.md` 中注入“成本指南”，指引 Agent 串行调用、先查 metadata 再拉 body。

---

## 5. 核心测试不变量断言矩阵 (INV-01 ~ INV-08)

- **INV-01 (Token 零暴露)**: 扫描所有 Prompt、Traces 日志与消息，断言 Token 字符串无明文泄露；
- **INV-02 (状态机确定性)**: 未连接调用必须抛出结构化 `not_connected` 与 `authUrl`，绝不静默放行；
- **INV-03 (卡片协议优先)**: 未连接状态下，Agent 输出断言必须包含 `[widget:connector_auth?...]` 语法；
- **INV-04 (双层权限硬拦截)**: Action 为 `DENY` 时必抛 `ActionPermissionDenied`；`ASK` 时必挂起等待审批；
- **INV-05 (硬限流窗口拦截)**: 60 秒内消费超标请求拦截率 100%，必须附带 `retry_after_seconds`；
- **INV-06 (写操作文件暂存)**: 高危写操作必须包含 `--upload` 文件暂存，否则执行器拒绝派发；
- **INV-07 (多账号强隔离)**: `--account <id>` 路由跨越或非法 account 抛出 `AccountNotFoundError`；
- **INV-08 (负向边界遵从)**: 变更文件集合严格限制在连接器运行时扩展层，禁止侵入认知五阶段核心代码。

---

## 6. 实施里程碑计划 (Milestones)

1. **M1: 连接器运行时底座与状态机** (`lca/infrastructure/connectors/core/`)
2. **M2: 首个切片 Gmail CLI 封装、Manifest 与 SKILL.md 自动注入**
3. **M3: LobeHub 卡片协议联动与 Prompt 先验认知注入 (`ConnectedServicesSection`)**
4. **M4: 双层正交权限引擎与滑动窗口硬配额执行器**
5. **M5: 全链路单测回归 (INV-01 ~ INV-08) 与端到端活体验证**
