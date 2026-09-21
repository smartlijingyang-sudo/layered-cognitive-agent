# 架构设计文档：助理创建向导、网关 Resume 路由与 Profile 合流全链路重构

**日期**：2026-09-21  
**状态**：Approved / Ready for Planning  
**关联 ADR / Note**：ADR-0187、ADR-0242、ADR-0173、ADR-0246  

---

## 1. 背景与根因剖析（Root Cause Summary）

在近期对话创建助理的端到端真实测试中，暴露了三个相互交织的深层缺陷：

1. **环境与能力缺位（Profile 割裂）**：
   - LCA 生产进程及启动脚本（`./scripts/lca-ops`、`lca_kernel serve`）默认加载 `profiles/web-standard.yaml`。
   - ADR-0187 与 ADR-0242 将 `create_assistant` 等原生助理工具放在了 `profiles/web-assistant.yaml`（通过 `bundles/assistant-runtime.yaml` 引入）。
   - 导致对外提供服务的运行时天生缺失助理域工具，用户下达「帮我创建一个助理」时，模型处于“无工具可用”的境地。

2. **工具降级诱导与内部向导严重泄露**：
   - 缺少原生 `create_assistant` 工具时，模型因 Prompt 中 `search_skill` 工具的宽泛描述（“不会做的任务先搜这里”）及候选技能列表中的 `create-assistant`，被误导调用 `search_skill` / `activate_skill("create-assistant")`。
   - `create-assistant/SKILL.md` 中包含不当指令（“无工具则告知用户需 web-assistant profile”），导致模型在 Step 2 检查失败后，将底层 Profile 配置名词和内部五状态向导代码全盘作为解释输出给最终用户。

3. **网关 Resume 模糊寻址与 409 竞态（用户输入丢失）**：
   - 当 Run A 触发 `askUserQuestion` 挂起进入 `waiting_input` 等待用户回答时，前端因刷新或重试发起了新 Run B，覆盖了 Topic 级别的 `latest_run`。
   - 用户在前端提交对 Run A 的答复时，网关 `_dispatch_resume` 依靠 `store.get_latest_for_topic(topic_id)` 寻址，错误命中了正在运行的 Run B。
   - 网关因 Run B 状态为 `running` 直接返回 `409 Conflict: run not waiting for input`，把用户填写的重要答案彻底丢弃。

---

## 2. 第一性原理与架构目标

1. **服务开箱即具备一等公民能力**：
   面向最终用户的生产服务必须默认具备完整的助理管理与创建能力，严禁将生产核心链路拆分成互不兼容的“残废版”与“完整版”。
2. **因果链精确绑定（因果不变性）**：
   一次特定的人机交互或选项提交，在因果链上是与产生该问答的具体 `run_id` 强绑定的。网关必须通过显式 `run_id` 严格路由，严禁基于易变的会话级最新指针猜测。
3. **实现细节对用户透明**：
   内部 Profile 名称、状态机节点编码、底层配置路径对最终用户严格透明。提示词必须规范 Agent 行为，严禁“教用户当运维”。

---

## 3. 三层重构设计方案

### 3.1 第一层：平台服务与 Profile 合流（能力就绪）

#### 3.1.1 默认 Profile 升级
- 将 `./scripts/lca-ops` 中 `kernel_serve` / `start` 以及相关测试/启动默认指定的 Profile 升级为 `profiles/web-assistant.yaml`（或确保基础 web 链路完整加载 `bundles/assistant-runtime.yaml`）。
- 确保内核启动后天然暴露 `create_assistant`、`create_assistant_skill` 等原生工具。

#### 3.1.2 软化 Composio 阻断依赖
- 检查 `profiles/web-assistant.yaml` 中 `lca-composio-provider` 的 `required: true` 限制。
- 将 `COMPOSIO_API_KEY` 改为非阻断式软加载（未配置 Key 时静默跳过或置为未激活，不触发 `ProfileResolveError` 阻断全栈启动）。

---

### 3.2 第二层：网关 Resume 路由精准绑定（消除 409 竞态）

#### 3.2.1 协议升级（`run_id` 优先）
- 修改 `CreateRunRequest`（在 `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py` 及相关契约）：
  - 允许在请求体中直接传递显式 `run_id`（或在 `resume_approval` / `resume_tool_result` 结构中携带）。
- 重构 `_dispatch_resume`：
  ```python
  # 优先采用请求体中明确声明的 run_id
  target_run_id = (
      body.get("run_id")
      or (decoded.resume_approval and decoded.resume_approval.run_id)
      or (decoded.resume_tool_result and decoded.resume_tool_result.run_id)
  )
  if not target_run_id:
      # 仅当没有指定任何 run_id 时，作为历史兼容回退到 topic 最新 run
      target_run_id = str(row.get("run_id") or "")
  ```

#### 3.2.2 前端提交对齐
- 确保前端在通过 `/runs` 提交 `askUserAnswers` 时，在请求体中携带原问答插件消息上记录的 `lca_run_id`。

#### 3.2.3 状态校验与防御
- 当指定 `run_id` 的会话处于 `WAITING_INPUT` 时，正常唤醒恢复；
- 若已被终结，返回语义清晰的错误，而不是与其它并发 Run 发生混淆。

---

### 3.3 第三层：Skill 提示词清理与五步向导闭环（优雅交互）

#### 3.3.1 清理垃圾提示词
- 重构 `/home/lichao/.lca/skills/create-assistant/SKILL.md`（以及仓库内置对应的模版）：
  - 彻底删除“工具列表必须有 create_assistant，没有则告知用户需 web-assistant profile”等运维暴露语句；
  - 彻底删除将五状态内部节点名字背诵给用户的行为。

#### 3.3.2 规范五步创建向导 SOP
1. **STATE 1: 部门/领域探测**：通过 `askUserQuestion` 友好展示主流领域选项（工程技术、市场营销、综合专业、设计等），允许用户点选或直接描述。
2. **STATE 2: 角色确定**：展示领域热门专家角色，或提供“自定义角色”选项。
3. **STATE 3: SOUL 对齐**：生成符合规范的 SOUL 草稿（包含身份、性格、能力、语气四段，长度>=200字），引导用户确认或微调。
4. **STATE 4: 名称确认**：给出 2-3 个推荐名称，并支持用户自定义名称。
5. **STATE 5: 执行物化**：调用 `create_assistant` 原生工具完成助理 Home 创建并在 Postgres/前端投影，最后向用户输出精致的名片式汇报（名字、ID、性格、能力、前端入口链接）。

#### 3.3.3 工具描述调优
- 调整 `search_skill` 工具描述中的引导性语句，去除强行推荐的倾向，保持客观功能描述。

---

## 4. 验证与验收矩阵

| 验证项 | 验证手段 | 预期结果 |
|---|---|---|
| **Profile 完整性** | `./scripts/lca-ops kernel_check profiles/web-assistant.yaml` | 编译正常，包含全部 14 个 phase/subgraph 与助理工具 |
| **内核服务就绪** | 重启内核并调用 `GET /health` | 状态健康，工具列表具备 `create_assistant` |
| **网关 Resume 精准性** | 单元/集成测试模拟并发 Run 下带 `run_id` resume | 成功唤醒目标 Run，无 409 Conflict，用户输入 100% 消费 |
| **端到端创建向导** | 对话执行「帮我创建一个助理」 | 正常唤起问答选项，对齐 SOUL，调用 `create_assistant` 成功生成助理，无内部名词泄露 |
