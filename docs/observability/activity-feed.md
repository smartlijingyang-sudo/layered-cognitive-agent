# Activity 动态栏：数据是什么、UI 怎么显示

> 对应截图：任务详情视图「验证Activity重启与事件完整性」、助手动态栏「今天」分组。
> 代码版本：main @ 87cdb25a1（2026-10-03）。

## 一、图里是什么

### 图 1 / 图 3：任务执行详情视图

这是一个**任务**（task）的执行轨迹面板，标题「验证Activity重启与事件完整性」，右上角「已完成」是任务终态。

- **左侧**：步骤清单。✓ 是已完成的步骤（读代码、建 worktree、跑验证脚本……），◐/□ 是待办。点击步骤，右侧显示该步骤产出的**证据**。
- **右侧**：代码证据 + 验证结论。展示了从 `activity_projector.py` 提取的两段代码：
  - `__init__`（88–100 行）：字段初始化与冷启动分支——无缓存文件且 `seed_traces=True` 时调 `seed_from_traces()`。
  - `seed_from_traces`（270–284 行）：冷启动时从 `traces/runs` 恢复活动的入口逻辑。
  - 结论：冷启动路径已覆盖，信息完整，无执行错误。

### 图 2：助手动态栏（Activity Feed）

这是**助手右侧抽屉**的「动态」tab（`AssistantStatusDrawer.tsx`），按 `今天 / 昨天 / 更早` 分组。每一行就是一个 **Activity**：

| 行内元素 | 含义 | 例子 |
|---|---|---|
| 标题 | 工具做了什么（一句话） | 验证Activity重启与事件完整性 |
| 摘要 | 关键结果（一句话） | 验证重启后36个活动完整恢复 |
| 时间 | 开始时间（今天只显示 HH:MM） | 4:39 pm |
| 状态图标 | ✓ 已完成 / 运行中 / ✕ 失败 / 已取消 | ✓ |
| 工具徽标 | 实际工具名 | runCommand |

点击一行弹出**详情弹窗**：人读概述、调用工具与参数 JSON、产出结果、开始时间、耗时。

## 二、Activity 的信息是什么（数据模型）

`ActivityItem`（`lca/contracts/models/observability/activity.py`，frozen pydantic）：

| 字段 | 含义 | 来源 |
|---|---|---|
| `id` | 工具调用唯一标识 | `invocation_id` / `call_id`；回填的为 `seed:{run}:{step}:{idx}` |
| `tool_name` | **真实工具名**（以前丢了，前端只能显示 category） | 事件 payload |
| `title` / `summary` | 人读标题/摘要 | `ActivityIntentNamer.name()` 按工具类型生成 |
| `current_step` | **进行时在干什么**（running 才有，结束后清空） | `ActivityIntentNamer.live_step()`，如"正在浏览 example.com" |
| `status` | `running` / `completed` / `failed` / `cancelled` 四态 | end 事件的 `ok` / `outcome` / `ToolDenied` |
| `start_time` / `end_time` | 真实开始/结束（ISO，无则空串，不编造） | start 事件时间戳；`body.tool.execute.start` 会修正为真实执行时刻 |
| `duration_ms` | 耗时毫秒 | `latency_ms` |
| `category` / `icon` | 分类与图标 | 按工具名映射（COMMAND/SUBAGENT/BROWSER/CRON/TOOL） |
| `params` | 工具参数原文 | `arguments` / `args` |
| `result_summary` | 结果一句话（失败时带错误信息） | `result.state.summary` / `message.content` / `stdout_head` |
| `is_system` | 是否系统活动 | 事件标记 |

**Muse 思想**：没数据就空着，不编造（以前 `start_time` 缺失时硬编码 `"2026-10-02T00:00:00Z"`，`cancel` 时 `end_time` 写 `"cancelled"` 字符串——都已清除）。

## 三、UI 怎么显示这些（实现链路）

```
后端事件                    翻译层                    投影层                  API              前端
─────────                  ───────                    ───────                 ────             ────
spine: phase.tool.call.start ─┐
spine: step.tool_call.record ─┼─→ EventTranslator ─→ ActivityProjector ─→ status-snapshot ─→ AssistantStatusDrawer
spine: body.tool.execute.*  ──┘      │  feed_event()      │  get_activities()      │  (fetch + WS)
catalog: ToolStarted/Invoked/Denied ─┘                   │                      │
                                                         ▼                      ▼
                                              seed_from_traces()          快照映射 + 增量 patch
                                              (kernel 重启回填)
```

### 3.1 后端：事件 → ActivityItem

`EventTranslator.translate()` 按事件类型分发（`lca/application/runtime/coordinator/event_translator.py`）：

- **spine**（`execution_point`）：`step.tool_call.record` 是网关路径的工具启动信号（`phase.tool.call.start` 在网关被 `SUPPRESSED_SPINE_EPS` 压掉）；`body.tool.execute.start/end` 是真实执行边界。
- **catalog**（`event.type`）：`ToolStarted` / `ToolInvoked` / `ToolDenied`，网关工具事件的主通道（曾因只认 `execution_point` 而整条断掉，已修）。

`ActivityProjector.feed_event()`（`lca/infrastructure/observability/activity_projector.py`）：

- **start**：建 `RUNNING` 项，`current_step = live_step(tool, args)`（分工具类型的进行时语言）。
- **execute.start**：把 `start_time` 修正为真实执行时刻（空壳事件无 tool 身份时优雅丢弃）。
- **end**：落 `completed` / `failed`（`ToolDenied` 必红，错误信息进 `result_summary`）/ `cancelled`，清空 `current_step`。
- **重启恢复**：`seed_from_traces()` 从 `traces/runs/*/journal.json` 回填最近 50 个 run 的 `tool_calls`/`tool_results`；`get_activities()` 冷启动时懒加载一次。**只取已落盘的 completed/failed**——重启时刻"running"的已经死了，显示成运行中就是撒谎。

### 3.2 前端：AssistantStatusDrawer.tsx

**快照**：打开抽屉调 `/lca-api/v1/assistants/{id}/status-snapshot` → `activities[].model_dump()` → 映射为行数据：

- `status`：`completed→success` / `running→running` / `failed→error` / `cancelled→cancelled`（`mapBackendStatus`）。
- `timestamp`：`formatActivityTime()`——今天 HH:MM，昨天"昨天 HH:MM"，更早"MM-DD HH:MM"；无时间戳显示"—"。
- `toolBadge` / 详情 `toolName`：用真实 `tool_name`（以前误用了 `category`）。
- `dateGroup`：按日期分今天/昨天/更早三组。

**增量**：WebSocket `activity_updated` → `window` 事件 `lca:activity_updated` → 原地 patch 单行（`toolName`/`currentStep`/`resultSummary`/`durationMs` 全量透出）。

**进行时**：`running` 的行每秒 tick 显示 elapsed（"运行中 · 3分12秒"），摘要区显示 `currentStep`（"正在浏览 example.com"）而非静态 summary；右侧有"停止"按钮调取消接口。

**详情弹窗**：状态 Tag 按实际四态渲染（以前硬编码"✓ 执行成功"）；"调用工具"显示 `toolName(参数名)` + 参数 JSON；"产出"显示 `result` 或"—"（以前没结果时撒谎写"✓ 动作已完成"）；"耗时"用 `formatDuration`（`1.2s` 而非 `1200ms`，无则"—"）。

### 3.3 已知的诚实边界

- **直连 kernel 的 run**：spine 工具事件按 ADR-0220/0240 有意只带 `state_id`（富信息留给 control-plane），translator 静默丢弃——这类 run 的动态栏目前为空。网关（web UI）路径完整。
- **`body.tool.execute.start` 刷新**：生产 spine 目前不带富 payload，该分支为防御性代码，当前实际开始时间取自 `step.tool_call.record` / `ToolStarted`（毫秒级差异）。

## 四、测试

- `tests/infrastructure/observability/test_activity_live.py`：11 个新行为测试（tool_name 落盘、live_step 分类型语言、execute.start 刷新、catalog 建项/拒绝、失败带错误、cancel 语义、回填 3 个）。
- `tests/scenario/test_status_screen_invariants.py`：端到端不变量 6 绿。
- E2E：真实 trace 重放 + 网关路径全生命周期（`step.record → ToolInvoked` 走真实 translator）+ kernel 重启回填（36 个活动），全绿。
