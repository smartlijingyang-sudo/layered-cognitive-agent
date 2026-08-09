# ADR-0051: Run Workspace Plane — 统一运行平面

## 状态

Accepted

## 背景

ADR-0049（Resource/Evidence）、ADR-0050（Run-Bound Sandbox）、ADR-0048（Operational Skills）
各解决了子域问题，但两次生产 trace 暴露 **平面未闭合** 时的系统性失败：

| 症状 | 根因（非补丁目标） |
|---|---|
| Pipeline 922s 全员 canceled | 每 agent 独立 300s 墙钟，无 team 级 deadline 继承 |
| PDF 已生成但 answer 为空 | 产物在 Evidence 平面，Completion 平面未读 ArtifactLedger |
| surrogate 图表失败 | 执行平面 stdout 未过 SafeText 边界 |
| `.doc` 6 步试错 | Inspect 无 format profile → Skill 路由盲选 |
| sandbox_execute×3 循环 | Control 平面只 insight 告警，无 gate 熔断 |
| SSE 长时间静默 | 缺 team 级 Activity（本 ADR 预留；Phase 1 先闭合 Workspace） |

业界范式对齐：

- **LobeHub**：Session Workspace = 持久环境 + 产物注册 + activate/exec 闭环
- **OpenAI Code Interpreter**：Run-scoped kernel + auto file listing on completion
- **E2B**：Persistent sandbox + artifact harvest at `/outputs`
- **ADR-0049 三平面**：本 ADR 在 Execution/Evidence 之间引入 **Workspace** 作为 run 级单一入口

## 决定

### 一、RunWorkspace（L0，gateway 绑定）

一次用户 run（`session.run_id`）绑定一个 `RunWorkspace`：

```text
RunWorkspace
├── run_id          # 与 sandbox runtime / run_id_scope 同键
├── deadline        # team 级墙钟上限（utc）
└── artifacts       # ArtifactLedger（run 级产物账本）
```

- 绑定：`gateway.execute_run` 入口 `run_workspace_scope(deadline=…)`
- 访问：`get_run_workspace()` — 与 `get_current_run_id()` 同 contextvar 穿透模式
- 销毁：`finalize_run` 与 sandbox unbind 同生命周期

### 二、ArtifactLedger（Evidence ⊂ Workspace）

- 每次 sandbox 工具成功产出 `files` → `ledger.record(...)`
- **Completion 收口**：loop 退出且无 `respond` 时，从 ledger 合成用户可见 closure
- **Pipeline 接力**：`handoff_block()` 注入下一成员 task（路径 + MIME，非猜测）
- 对标 LobeHub execScript 产出 + OpenAI run file annotations

### 三、Team Deadline 继承（Resource 闭合）

- 常量：`DEFAULT_RUN_WALL_CLOCK_SECONDS = 900`（team/solo gateway run 默认）
- `CognitiveAgent.run`：`effective_wall = min(agent_cap, deadline_remaining)`
- 成员不再从 0 开始计 300s；Pipeline 串行共享同一 deadline
- `RunContext.deadline` 从 workspace 注入 transport 委派链

### 四、Completion Plane（Control 闭合）

1. **Terminal reserve**：`TERMINAL_RESERVE_STEPS = 1` — 最后一步仅允许 `respond|stop`
2. **TerminalRespondGate**：末步若 LLM 仍选 `use_tool` → 强制 `respond` + ledger closure 文本
3. **DefaultStopOutcomePolicy.resolve_budget_exceeded**：有 artifact → COMPLETED + closure
4. 消除「10 步全 use_tool、output_text 为空」类失败

### 五、ToolLoopBreakerGate（Control 熔断）

- 同一 `(tool_name, error_kind)` 连续 ≥3 次 → 短路为带 `suggested_fix` 的 synthetic observation
- 下一轮 gate 强制换策略（禁止相同 tool 第四次）
- InsightEngine loop_warning 保留为投影；gate 为机制

### 六、SafeText Boundary（Execution → Narrative）

- 单一函数 `sanitize_stream_text()` — surrogate → U+FFFD
- 应用于：Onlyboxes stdout/stderr、`SandboxStreamEmitter`、journal preview 边界
- 输入 code 仍用现有 `_strip_surrogates`（JSON 安全）

### 七、Inspect Format Profiles（Execution 增强）

- `.doc` → `type: legacy_word`, `hint: python-docx 不支持；可用 olefile 或 libreoffice 转换`
- 预装 `olefile` 入 baseline（与 ADR-0048 文档类扩展一致）
- profile 含 `suggested_skills` 字段供 prompt 路由（MIME → skill 映射表）

### 八、Agent 级 Decision Gate 链（全 agent，非仅 lead）

- `ChainedDecisionGate(ToolLoopBreakerGate(), TerminalRespondGate())` 注入所有 `ModularBrain`
- Lead 专有 gate（MustConsultAll）在其后链接，语义不变

## 后果

- 正向：一次绑定闭合 Resource/Evidence/Completion；Pipeline 产物可接力；中文图表 surrogate 不再 infra 失败；`.doc` 有明确路径。
- 负向：`ModularBrain` 构造参数扩展；gateway run 默认墙钟 900s（可 env 配置后续迭代）。
- 测试：`test_run_workspace.py`、`test_decision_gates_workspace.py`、inspect olefile baseline。

## 关联

- Extends：ADR-0049、ADR-0050、ADR-0048
- Does not supersede：五层分层、Journal-as-Truth

## Phase 2 — Stream / Activity / Skill Routing（已实现）

### 九、StepTextDelta 双通道

- `StreamChannel`: `decision` | `answer`
- L0 `classify_output_channel()` — JSON 工具决策 vs 用户可见 prose 分离
- `TelemetryLLMAdapter` 发射带 `channel` 的 `StepTextDelta`
- 前端 `chat-projector` / `turn-timeline-projector` 仅 `answer` 通道更新 finalAnswer

### 十、Run Activity 心跳（SSE 静默消除）

- Journal 事件：`LlmCallStarted`（调用锚点）、`RunActivity`（5s LLM 心跳 + 工具启动）
- L0 `LlmStreamActivityTracker` — 无 delta 时发射 `RunActivity(phase=llm_thinking)`
- L1 `SafeExecutor` — `ToolStarted` 后发射 `RunActivity(phase=tool_running)`
- 前端：`ActivityBlock` + `RunProgressBar.activityDetail` + `AssistantTurnView` 进度文案

### 十一、MIME → Skill 路由

- L0 `format_routing.py` — extension / inspect profile → `suggested_skills`
- Inspect enrich 写入 workspace profile；Reasoner 注入 `{suggested_skills}` prompt 段
- 全部 brain prompt（react / hierarchical / routing）含 `SUGGESTED_SKILLS` 优先级链

### Phase 2 测试

- `test_stream_channel.py`、`test_format_routing.py`
- 前端：`chat-projector.test.ts`、`turn-timeline-projector.test.ts` channel/activity 用例
