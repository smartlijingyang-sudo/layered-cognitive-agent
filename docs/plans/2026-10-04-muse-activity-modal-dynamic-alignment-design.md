# Muse 活动动态弹窗高保真对齐与生产者真值归一架构设计规范 (方案 A+)

> **文档版本**: 1.0.0  
> **创建日期**: 2026-10-04  
> **状态**: Approved (已获用户全量 4 节逐项审批确认)  
> **自治等级 (Autopilot Level)**: DRAFT (涉及关键事件生产者写入契约、Journal Fold 派生模型与前端观测 UI，需高标准 TDD 验证)  
> **对照基准**: Meta Muse 生产实机截图（`activity-drawer-today.png`, `activity-task-detail-coldstart.png`, `activity-task-detail-grep.png`）  

---

## 1. 背景与核心问题诊断

在 LCA 现有的助手右侧抽屉「动态」弹窗（任务详情双栏弹窗）中，前期实现存在以下三类严重偏离真实工程语义的问题：

1. **重复步骤条目（Duplicate Steps）**：
   - 在 `journal_fold.py` 中，收到 `llm.request.header.assistant` 时，以 `invocation_id=""` 创建了 `ToolCallRecord` 并加入 `target.tool_calls`；随后 `step.tool_call.record` 携带有真实 ID（如 `toolu_...`）到达，因 ID 无法匹配，导致合并逻辑再次追加一条相同的记录。
   - 类似地在 `tool_results` 中，`step.tool_result.record` 与 `body.tool.execute.end` 分别携带不同的 ID（`toolu_...` vs `decision_...`），导致执行结果被重复追加。
   - 最终在 `query_endpoints.py::_read_run_journal_detail` 中解构出完全相同的镜像步骤（例如 `step-005-1` 与 `step-005-2`）。
2. **硬编码与假数据填充（Mock Illusion）**：
   - `activity.py::parse_step_evidence` 中充斥着死常数（写死 `3841ms` 耗时、从 stdout 文本挖掘 `ZZSTART` 边界标记、假 `pytest 9.0.1` 输出、写死 `asst_3dacffc01a90` 路径等）。
   - `AssistantStatusDrawer.tsx` 中首步骤 `● 已开始` 的 fallback 写死了 `'验证Activity重启与事件完整性'`（历史截图标题）；右栏叙述与结论充斥着机械模板套话。
3. **状态机与失败流脱节**：
   - 弹窗顶部状态未与底层真实 Run 终态（`manifest.outcome`、`error`）联动；
   - 步骤状态图标缺乏 Muse 截图中的真实工程语义（如文件创建 `📄`、命令执行 `✔`、失败 `✕`、运行中 `◐`）；
   - 失败时缺乏真实退出码、标准错误与针对性根因分析。

---

## 2. 架构边界、自治等级与核心哲学

### 2.1 架构边界 (Owns & Does NOT Own, AP-01)
* **Owns（本次构建）**：
  1. **生产者事件契约收敛**：规范 `llm.request.header.assistant` 写入职责（仅记录模型预测意图 `predicted_intents`，严禁直接触碰 `target.tool_calls`）；
  2. **调用身份全链透传**：在 `dispatch` 入口铸造全局唯一稳定 `invocation_id`，统一 `step.tool_result.record` 与 `body.tool.execute.end`，消除 `toolu_...` vs `decision_...` 的双写割裂；
  3. **真值元数据上移**：在工具执行器与 `SafeExecutor` 处直接填充真实 `duration_ms`、`exit_code`、`stderr`、`stdout`，废弃 `ZZSTART` 文本挖掘标记与伪造数据；
  4. **Fold 引擎退化与 COMPAT Shim**：`journal_fold.py` 改为纯确定性的按 `invocation_id` group-by，彻底消灭启发式多维猜谜；仅保留严格前驱单条匹配作为历史脏 Journal 的过渡兼容 Shim（声明具体 delete-when）；
  5. **纯函数状态机与契约模型纯净化**：实现 `deriveStepState(tool_category, lifecycle_phase, exit_code, ok, is_live) -> StatusIcon`，清理 `activity.py` 里的全部硬编码魔数；
  6. **前端双栏高保真补丁**：重构 `AssistantStatusDrawer.tsx`，对齐 Muse 实机截图（极简胶囊药丸、无技术标签时间轴、真实 5 要素证据面板）。
* **Does NOT Own（严格禁止越权修改）**：
  1. 严禁改动五相认知循环语义（C1 认知闭集，不修改 `perceive → think → act → reflect → remember` 核心时钟）；
  2. 严禁触碰工具沙箱执行窄门（C10 执行窄门，不改动 `SafeExecutor` 与 `Sandbox` 隔离语义）；
  3. 严禁在观测路径引入控制面副作用（C7 控制面与观察面严格分离）；
  4. 严禁修改外部宿主机资产或提交任何非 LCA 框架核心代码（AGENTS.md 铁律）。

### 2.2 核心哲学：生产者责任制 (Producer Invariant Discipline)
* **真实即唯一**：谁产生事实，谁负责记录事实的完整元数据（退出码、毫秒耗时、标准错误）。
* **读模型零猜测**：Fold 派生层只负责聚合与投影，严禁对生产者的异形事件做实体同一性启发式猜谜，严禁为了画面好看而伪造不存在的耗时或返回内容。
* **单向身份流**：身份在 dispatch 时只铸造一次，贯穿执行、回执、报错与反思生命周期，生到死不变。

---

## 3. 生产者改动清单与身份全链透传契约

### 3.1 身份生命周期契约：dispatch 处一次铸造、生到死透传
* **铸造唯一性**：在 `ReAct` 决策生成 `ToolCall` 或在 `Body.dispatch_tool_calls` 入口处，**一次性铸造**全局唯一的稳定 `invocation_id`（如 `toolu_...` 或 `call_...`）。
* **全生命周期原样携带**：
  ```text
  ToolCall.call_id (铸造)
         │
         ▼
  SafeExecutor.execute(..., invocation_id=call_id)
         │
         ├─→ record_step_tool_call(invocation_id=call_id)  [step.tool_call.record 事实]
         ├─→ commit_body_tool_execute_start(invocation_id=call_id)
         │       │
         │       ▼ (执行 sandbox / 本地进程)
         │
         ├─→ commit_body_tool_execute_end(invocation_id=call_id, exit_code, latency_ms)
         └─→ record_step_tool_result(invocation_id=call_id, exit_code, latency_ms, stderr) [step.tool_result.record 事实]
  ```
* **阻断双重身份**：外层 `decision.decision_id`（如 `decision_4f9e...`）仅作为因果追踪的 `causation_id` 或 `span_id`，**严禁将其篡改为单个工具调用的 `invocation_id`**。

### 3.2 生产者改动清单 (Producer Changes Inventory)

| 生产者 Execution Point | 发生位置 | 原现状（病根） | 方案 A+ 改造契约（消灭猜谜） | 消除的坏味道 / 假象 |
|---|---|---|---|---|
| **1. `llm.request.header.assistant`** | `ModelVisiblePublisher` | 解析 LLM 输出的预选工具，以 `invocation_id=""` 创建 `ToolCallRecord` 并直接追加到 `target.tool_calls`。 | **类型级隔离**：<br>1. 改写为 `PredictedIntent`，仅存放在 `target.thinking.predicted_intents` 元数据中；<br>2. **严禁触碰 `target.tool_calls`**。实际执行的 `tool_calls` SSOT 生产者收敛且仅为 `step.tool_call.record`。 | **从源头物理消除孪生条目**（彻底根治 `step-005-1` 与 `step-005-2` 重复问题）。 |
| **2. `body.tool.execute.end`** | `SafeExecutor._execute_once` | 与 `step.tool_result.record` 分别携带不同 ID（`decision_...` vs `toolu_...`）发送，在 `journal_fold.py` 中两者均调用 `_assign_tool_result`，导致结果被追加两次。 | **职责单一化与 ID 归一**：<br>1. `body.tool.execute.end` 强制透传真实的 `invocation_id=call_id`，并声明仅作为生命周期括弧；<br>2. `journal_fold.py` 确立 `step.tool_result.record` 为唯一的 ToolResult 事实，`body.tool.execute.end` 不再重复调用 `_assign_tool_result`。 | 彻底消除 `tool_results` 数组中混杂 0ms 空 stdout 决策记录的双写问题。 |
| **3. `step.tool_result.record`** | `SafeExecutor.execute` | Payload 仅包含 `latency_ms`、`stdout_head`、`stderr`，缺少结构化的 `exit_code`。 | **真值字段上移**：<br>1. 在 `record_step_tool_result` 的 Payload 中增加强类型字段 `exit_code: int`（从 `SandboxResult.exit_code` 或进程退出码直接提取，成功默认 0，失败默认真实非 0 码）；<br>2. 真实透传 `latency_ms`、`stderr`、`stdout_truncated`。 | 读模型与前端无需从 stdout 猜退出码，真实失败退出码直出。 |
| **4. `activity.py::parse_step_evidence`** | 派生读模型 | 从 stdout 文本挖掘 `ZZSTART`，包含 `3841ms` 写死常数、`pytest 9.0.1` 伪造文本、`asst_3dacffc01a90` 路径绑定。 | **退化为纯渲染函数**：<br>1. 彻底删除 `3841ms`、`ZZSTART` 启发式检测、fake pytest、写死助理 ID 等全部死代码；<br>2. 元数据完全由入参 `tool_result` 中的 `duration_ms`、`exit_code`、`stderr` 纯函数透传；若无数据则输出 `—`，严禁编造。 | 彻底消灭系统代码中的“假数据与硬编码”，完全践行诚实纪律。 |

### 3.3 Fold 引擎退化与历史数据 COMPAT Shim
1. **新数据处理**：
   - 收到 `step.tool_call.record`：根据其自带的 `invocation_id` 直接放入 `target.tool_calls`；
   - 收到 `step.tool_result.record`：按相同 `invocation_id` 直接关联至对应的 tool_call，**零启发式多维匹配**，纯按 ID 做 group-by。
2. **COMPAT Shim（仅针对历史脏 Journal，带严格边界与 delete-when）**：
   - **适用范围**：仅当 `target.tool_calls` 中存在历史改版前生成的空 ID 记录时生效；
   - **严格约束**：仅允许合并“紧邻的前一条未匹配记录”，**严禁跨多条扫描**，防止误吞连续两个同名同参数的独立调用；
   - **Delete-When**：设置明确的删除条件与退役标记（`# COMPAT: clean up after legacy run traces migration, owner: observability, delete-when: v1.0-release`）。

---

## 4. 纯函数状态机与 Muse 高保真双栏渲染架构

### 4.1 纯函数状态机 (Pure-Function State Machine)
```typescript
export type StepIconType = 'started' | 'completed' | 'file_op' | 'error' | 'running';

export function deriveStepState(
  phase: string,
  toolName?: string,
  exitCode?: number,
  ok: boolean = true,
  isLive: boolean = false
): { iconType: StepIconType; iconSymbol: string; color: string } {
  if (phase === 'Lifecycle → Started' || phase === 'started') {
    return { iconType: 'started', iconSymbol: '●', color: '#aaaaaa' };
  }
  if (isLive) {
    return { iconType: 'running', iconSymbol: '◐', color: '#60b1ff' };
  }
  if (!ok || (exitCode !== undefined && exitCode !== 0)) {
    return { iconType: 'error', iconSymbol: '✕', color: '#f4416c' };
  }
  const fileOpTools = new Set([
    'write_to_file', 'create_script', 'edit_file', 'replace_file_content', 
    'multi_replace_file_content', 'touch', 'update_file'
  ]);
  if (toolName && fileOpTools.has(toolName)) {
    return { iconType: 'file_op', iconSymbol: '📄', color: '#cccccc' };
  }
  return { iconType: 'completed', iconSymbol: '✔', color: '#c4f042' };
}
```

### 4.2 真实失败流与错误贯穿机制
* **顶层 Run 状态动态联动**：
  弹窗顶部胶囊药丸以 `runDetail.status`、`manifest.outcome` 或各步骤的 `exitCode` 动态联动：
  - 失败时呈现红色胶囊药丸：`✕ 执行失败`（背景 `#2a1215`，文字 `#f4416c`）；
  - 成功时呈现浅绿底深绿字胶囊药丸：`✓ 已完成`（背景 `#132c18`，文字 `#c4f042`）；
  - 运行中呈现浅蓝底深蓝字胶囊药丸：`● 进行中`（背景 `#111d2c`，文字 `#60b1ff`）。
* **步骤级失败要素还原**：
  失败步骤右栏直接展现真实底层错误数据：
  1. **命令代码块**：真实执行的失败命令；
  2. **元数据点标**：`· 退出码: 1, 耗时: 120ms`（真实非 0 退出码红标高亮）；
  3. **错误内容块**：直接输出真实 `stderr` 或 `tr.error`，不再提示“未知错误”；
  4. **验证结论**：直接输出 `验证结论：动作执行未达预期（退出码 1）。原因：${tr.error || stderr_summary}。`

### 4.3 彻底对齐 Muse 实机截图的信息流与视觉规范
对照 `activity-task-detail-coldstart.png` 与 `activity-task-detail-grep.png`：
1. **Header 区域**：
   - 左上角：圆角状态胶囊药丸（`已完成` / `进行中` / `执行失败`）；
   - 药丸下方：任务大标题（`20px`, `700` 加粗白色，动态取自 Run Objective）；
   - 右上角：关闭按钮 `✕`；
   - **彻底清除**：删除 `"Run: run_16bb..."` 调试字符串。
2. **左栏步骤树 (Timeline Sidebar)**：
   - 移除 `"本次思考与调用概要"` 赘述标题；
   - 真实纵向贯穿线，依序排列：
     - 首节点：灰色小实心圆点 `● 已开始`；
     - 中间步骤：按纯函数状态机渲染（`✔`、`📄`、`✕`、`◐`）+ 简洁的自然语言动作标题；
     - 选中项：圆角深色高亮背景矩形（平滑切换）。
3. **右栏 5 大高保真证据面板 (Evidence Pane)**：
   - **要素 1（标题与动作说明）**：
     - 二级粗体大标题（如 `在LCA代码中检索重建与状态恢复相关函数`）；
     - 直接紧接动作自然叙述（**彻底删除“🧠 智能体意图与执行叙述”冗余小标题**），从 Thinking 首句或根据工具动作语义动态生成。
   - **要素 2（执行的命令::）**：
     - 标题写为 `执行的命令::`，后接 `bash` 语法高亮代码块，右上角常驻复制与下载图标。
   - **要素 3（元数据点标）**：
     - 抛弃多色 antd Tag，还原为截图中的极简文本点标：
       `· 退出码: 0, 耗时: 120ms`
       （仅在真实发生截断时展示：`· 输出已通过边界截取`）。
   - **要素 4（提取内容 / 检索结果）**：
     - Grep/搜索类操作：标题 `检索结果：`，呈现结构化编号列表 `1. path/file:line - match`；
     - 代码/文件读取类操作：标题 `提取到的代码内容`，呈现带行号的代码块及复制/下载按钮。
   - **要素 5（验证结论）**：
     - 独立小节标题 **`验证结论`**（加粗白色）；
     - 真实动态结论段落（无执行错误 / 具体的校验成功声明 / 失败时的根因分析）。

---

## 5. 自动化测试断言矩阵与不变量守卫

| 不变量 ID | 不变量描述 | 验证目标 | 责任测试文件 |
|---|---|---|---|
| **INV-01** | **唯一身份生命周期透传** | 铸造的 `invocation_id` 在 `step.tool_call.record`、`commit_body_tool_execute_start/end` 和 `step.tool_result.record` 中 100% 完全相同；严禁空串 `""`，严禁用 `decision_id` 覆盖工具 ID。 | `tests/loop/test_tool_invocation_id_lifecycle.py` |
| **INV-02** | **生产者职责隔离与零双写** | `llm.request.header.assistant` 严禁向 `target.tool_calls` 添加记录（仅记录为预测意图）；`tool_calls` 唯一由 `step.tool_call.record` 单写；彻底消除孪生步骤。 | `tests/session/derivers/test_journal_fold_zero_duplicate.py` |
| **INV-03** | **真值字段上移与退出码契约** | `record_step_tool_result` 显式携带结构化 `exit_code: int` 与真实 `duration_ms`；严禁魔数（3841ms）、假 pytest 文本。 | `tests/cognition/body/test_tool_result_true_exit_code.py` |
| **INV-04** | **零文本挖掘与硬编码清零** | `parse_step_evidence` 退化为纯渲染函数；源码中彻底消灭 `ZZSTART` 文本猜状态、写死 `asst_3dacffc01a90` 路径等遗留代码。 | `tests/observability/test_activity_evidence_zero_hardcoding.py` |
| **INV-05** | **纯函数状态机确定性** | `deriveStepState` 纯函数无外部 I/O：文件类操作 `📄`、成功命令 `✔`、失败/非0退出码 `✕`、运行中 `◐`、首节点 `●`，100% 确定。 | `tests/deploy/test_step_state_machine_purity.py` |
| **INV-06** | **失败流端到端真实透传** | 工具执行失败时（exit_code != 0 或 exception），生成的 `StepEvidence` 必须携带真实退出码、真实 `stderr`、`iconType='error'`，验证结论体现真实根因。 | `tests/observability/test_step_evidence_failure_propagation.py` |
| **INV-07** | **前端弹窗 UI 补丁 Muse 对齐** | TSX 补丁彻底清除 `'验证Activity重启与事件完整性'` 兜底文本、清除 `"Run: run_xxx"` 调试文本、清除 `"🧠 智能体意图与执行叙述"` 小标题，状态药丸三态联动。 | `tests/deploy/test_assistant_status_drawer.py` |
| **INV-08** | **COMPAT Shim 严格边界与生命周期** | 历史数据兼容 Shim 仅允许合并紧邻的前一条未匹配预测记录，严禁跨多条扫描，声明明确的 `delete-when`。 | `tests/session/derivers/test_journal_fold_compat_shim.py` |
