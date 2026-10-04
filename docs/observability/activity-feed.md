# Activity 动态栏：数据是什么、UI 怎么显示

> 对应截图：任务详情视图「验证Activity重启与事件完整性」、助手动态栏「今天」分组。
> 代码版本：main @ 2f13df17e（2026-10-04）。**版本弧**：`634fe4c4c`（李超 10-03 17:09 亲改，重写投影）曾移除 `ActivityItem` 的 `tool_name`/`current_step` 字段与 `ActivityIntentNamer.live_step()`；`fix-activity-honesty-20261003-1730` 分支（`c9bcb5b51`，merge `f17a7effe`）把两字段加回，`d89fc6e73` 去掉了 auto-merge 引入的重复 `tool_name` kwargs；**`6b33b474d`（李超 10-04 01:28）删除了 `ActivityProjector`（可变缓存）与 `seed_from_traces`，换成纯 fold 架构 `lca/infrastructure/observability/activity_feed.py`**——一行不再是一个工具调用，而是一个 run；后端不再有事件增量写入。下文均为新架构状态。

## 一、图里是什么

### 图 1 / 图 3：任务执行详情视图（旧投影时期截图）

![任务详情：冷启动代码证据](images/activity-task-detail-coldstart.png)

![任务详情：grep 检索证据](images/activity-task-detail-grep.png)

这是一个**任务**（task）的执行轨迹面板，标题「验证Activity重启与事件完整性」，右上角「已完成」是任务终态。

- **左侧**：步骤清单。✓ 是已完成的步骤（读代码、建 worktree、跑验证脚本……），◐/□ 是待办。点击步骤，右侧显示该步骤产出的**证据**。
- **右侧**：代码证据 + 验证结论。展示了从（已删除的）`activity_projector.py` 提取的两段代码——作为旧投影架构的证据截图保留，新架构下该文件已不存在：
  - `__init__`（90–98 行）：字段初始化与冷启动分支——活动项为空且 `seed_traces=True` 时调 `seed_from_traces()`。
  - `seed_from_traces`（355 行起）：冷启动时从 `traces/runs` 恢复活动的入口逻辑。
  - 结论：冷启动路径已覆盖，信息完整，无执行错误。

### 图 2：助手动态栏（Activity Feed）

![助手右侧抽屉“今天”动态栏](images/activity-drawer-today.png)

这是**助手右侧抽屉**的「动态」tab（`AssistantStatusDrawer.tsx`），按 `今天 / 昨天 / 更早` 分组。**每一行就是一个 run**（新架构：`ActivityFeed.list_activities()` 一行一 run，不是旧架构的一行一工具调用）：

| 行内元素 | 含义 | 例子 |
|---|---|---|
| 标题 | run 的目标（一句话） | 验证Activity重启与事件完整性 |
| 摘要 | 工具调用汇总（一句话） | 验证重启后36个活动完整恢复 |
| 时间 | 开始时间（今天只显示 HH:MM） | 4:39 pm |
| 状态图标 | ✓ 已完成 / 运行中 / ✕ 失败 / 已取消 | ✓ |
| 工具徽标 | 该 run 首个工具名（`tool_name` 缺失时回退 `category`/`title`） | run_shell |

点击一行弹出**详情弹窗**：人读概述、调用工具与参数 JSON、产出结果、开始时间、耗时。

## 二、Activity 的信息是什么（数据模型）

`ActivityItem`（`lca/contracts/models/observability/activity.py`，frozen pydantic，`extra="forbid"`）。**新架构下一行 = 一个 run**，字段由 `activity_feed.py::_row_from_facts()` 从 fold 出的 `_RunFacts` 填充：

| 字段 | 含义 | 来源 |
|---|---|---|
| `id` / `run_id` | run 唯一标识 | `run_dir.name`（`traces/runs/<run_id>/` 目录名） |
| `assistant_id` | 助手绑定 | `""`——诚实声明不 scope：run 产物不带 assistant 绑定，硬填 `"default"` 会让无 scope 的 feed 看起来有 scope（`_row_from_facts` 注释原话） |
| `tool_name` | 该 run 首个工具名（`str`，默认 `""`） | `_RunFacts.tool_calls[0]` 的 name；既用于派生 category/icon，也落盘随快照透出前端 |
| `title` | run 目标一句话 | 清洗后的 objective（`_clean_objective` 去掉 perceive 阶段注入的 HTML 注释脚手架）/ 首工具名 / `运行 {run_id 后6位}`，截 60 字 |
| `summary` | 工具调用汇总 | `_summarize_tools`：`调用 N 个工具：a、b、c 等`（唯一名去重、只列前 3）；无工具调用时 `"未调用工具，直接回复"` |
| `current_step` | 进行时人读动作短语（`str \| None`） | 仅 `RUNNING` 行：最后一个工具的 `ActivityIntentNamer.name()` 短语；无工具时 `"智能体思考并回复中"` |
| `status` | `running` / `completed` / `failed` / `cancelled` 四态 | 未 terminated → `RUNNING`；terminated 按 outcome：failure/failed/error → FAILED，cancelled/canceled/stopped/interrupted → CANCELLED，其余 COMPLETED |
| `start_time` / `end_time` | 开始/结束（ISO） | terminated run 取 `journal.json` metadata 的 `started_at`/`closed_at`；live run 取 spine `kernel.run.start`/`kernel.run.stop` 的 `ts`；缺失 → `""`（`_iso(None)` 留空，不编造）。started_at 缺失时从 spine 开头回读 `kernel.run.start` 恢复（诚实恢复，非编造，见 §3.1） |
| `duration_ms` | 耗时毫秒 | `closed_at − started_at`（两端都有才算） |
| `category` / `icon` | 分类与图标 | 按首工具名映射（COMMAND/SUBAGENT/BROWSER/CRON/TOOL）；icon 走 `ActivityIntentNamer.name(first_tool)[2]`，无工具时 `"chat"` |
| `params` | 单次调用参数 | 默认 `{}`——run 级行不带单次调用参数 |
| `result_summary` | 结果一句话 | 默认 `None`——run 级行不带单次调用结果 |
| `is_system` | 是否系统活动 | 默认 `False` |

**Muse 思想**：没数据就空着，不编造——`_iso(None)` 返回 `""`；缺 `started_at` 时宁可花 256KB 预算去读 ledger 开头恢复真实时刻，也不编造；`assistant_id` 不 scope 就明写 `""`；遗弃 run（未结束又没人执行）直接不展示，不显示成"永远运行中"。

## 三、UI 怎么显示这些（实现链路）

```
run 账本（traces/runs/<run_id>/）        折叠层（读时重算）               API              前端
─────────────────────────────        ─────────────────               ────             ────
terminated run (manifest.json 在)      ┐
  journal.json（几 KB，全量）          ├─→ ActivityFeed.list_activities() ─→ status-snapshot ─→ AssistantStatusDrawer
live run（调用方传 live_run_ids）       ┘      （pure fold，无写盘）              │  (轮询 fetch)       │  (轮询 + tick)
  *.spine.jsonl（只读 4 种 marker）            │ memo 读缓存                      │
                                              ▼（按 artifact stamp 失效）
                                         按 start_time 倒序取最近 50
```

### 3.1 后端：账本 → ActivityItem（纯 fold，`6b33b474d` 起）

`ActivityFeed.list_activities(live_run_ids=())`（`lca/infrastructure/observability/activity_feed.py`，447 行）：**读时重算，零写盘**。设计依据 ADR-0167 D11：spine ledger 是唯一真值源，物化视图必须可重建——旧 `ActivityProjector` 的可变缓存是第二真值源，已被删除（与 ledger 漂移的实锤见 commit message）。

- **候选 run**：`traces/runs/` 下 `run_` 前缀目录，排除测试 harness 前缀（`run_test_`/`run_e2e_smoke_`）；按 mtime 取最近 400 个扫、最终返回最近 50 个。
- **terminated run**（`manifest.json` 在）：`_fold_journal()` 读 `journal.json`（几 KB 全量：metadata 的 objective/outcome/started_at/closed_at + steps 的 tool_calls）。
- **live run**（调用方 `live_run_ids` 说它还在跑）：`_fold_spine()` 读 `*.spine.jsonl`——子串预过滤只 parse 4 种 marker（`kernel.run.start`/`kernel.run.stop`/`phase.think.fold`/`step.tool_call.record`，其余整行跳过，GB 级账本不炸）；字节预算 64MB（`LIVE_SPINE_BYTE_BUDGET`，超了就断，达到它本身就是事故）。
- **遗弃 run**：未 terminated 且没人在执行——不进 feed（不显示"永远运行中"，这是诚实纪律）。
- **降级链**：journal.json 读坏/非 dict → 回退 fold spine；`started_at` 缺失（早夭 run 的 journal 里 `started_at` 仍是 0.0）→ `_spine_start_time()` 用 256KB 预算只读 ledger 开头找回 `kernel.run.start` 的真实时刻。
- **memo**：按 artifact 身份（文件名 + mtime + size）缓存 fold 结果——**读缓存**，丢了只重算，不做真值源；`invalidate()` 清空。

### 3.2 前端：AssistantStatusDrawer.tsx

**快照**：打开抽屉调 `/lca-api/v1/assistants/{id}/status-snapshot`（后端 `status_screen.py` 调 `get_activity_feed().list_activities(live_run_ids=…)`）→ `activities[].model_dump()` → 映射为行数据：

- `status`：`completed→success` / `running→running` / `failed→error` / `cancelled→cancelled`（`mapBackendStatus`）。
- `timestamp`：`formatActivityTime()`——今天 HH:MM，昨天"昨天 HH:MM"，更早"MM-DD HH:MM"；无时间戳显示"—"。
- `toolBadge` / 详情 `toolName`：前端 `toolName: a.tool_name || a.category || a.title`（`f17a7effe` 的 honesty 恢复仍有效：后端返回该 run 首个真实工具名）。
- `dateGroup`：按日期分今天/昨天/更早三组。

**增量**：旧架构的 WebSocket `activity_updated` 已随 `ActivityProjector` 删除（`lca/` 全仓零引用）——现在是**轮询**：`pollTimer` 定时重拉 status-snapshot，`running` 行每秒 tick 显示 elapsed（"运行中 · 3分12秒"）；有 `currentStep` 时显示它（`act.detail?.currentStep ?? act.summary`），由 fold 时的 namer 短语生成；右侧有"停止"按钮调取消接口。

**详情弹窗**（双栏，0739281da 对齐 Muse UX）：左侧步骤树（首节点"● 已开始"+真实动作流，选中高亮）；右侧 **5 要素证据面板**——叙述卡片（`ev.narrative`，缺则回退 reasoning/toolName(参数) 拼装）、bash 高亮命令块（带复制按钮）、元数据 bullets（退出码/耗时）、代码提取-检索结果块、加粗验证结论（`ev.conclusion`，缺则"验证结论：动作执行完成，符合预期，无执行错误"）。状态 Tag 按实际四态渲染（以前硬编码"✓ 执行成功"）；"耗时"用 `formatDuration` → `1.2s` 而非 `1200ms`，无则"—"。

### 3.3 已知的诚实边界

- **feed 不 scope 到 assistant**：run 产物不带 assistant 绑定，`assistant_id=""` 明写；每个助手看到的都是同样的最近 runs（`status_screen.py` 注释原话）。要 scope 先得把绑定落盘到 run 上，这是后续项。
- **遗弃 run 不展示**：terminated 标记缺失且不在 `live_run_ids` 里的 run 不进 feed——旧架构会把它显示成永远 running，新架构直接不展示。
- ✅ **测试隔离已落地**：`tests/conftest.py` 通过 `LCA_RUNS_ROOT` 把整个 pytest 会话的 run 产物指到临时目录；`profiles/*` 的 `runs_root` 改为 `{from_env: LCA_RUNS_ROOT}`，生产 kernel 不设该 env，回落 `traces/runs`。`run_paths.default_runs_root()` 是唯一收口点。
- ✅ **`tool_name` / `current_step` 已恢复**：`634fe4c4c` 的移除被 `f17a7effe`（honesty 分支 `c9bcb5b51`）撤销，`d89fc6e73` 去重；新架构下 `tool_name`= 该 run 首个真实工具名，`current_step`= running 行的 namer 短语；前端 `AssistantStatusDrawer.tsx:1006/1012/1308` 已消费。
- ✅ **诚实边界有回归钉**：`tests/scenario/test_muse_activity_invariants.py`（INV-01 ~ INV-06，13 例）钉住场景级诚实边界（意图解构、证据溯源、抽屉纯自然语言、时间线拓扑、五要素证据结构、只读观测隔离）——注意其 fixture 里 `runner.py` 字符串是**模拟的任务证据数据**（旧架构时期的场景），不是对已删模块的引用。
