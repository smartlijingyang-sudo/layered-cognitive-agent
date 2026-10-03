# 架构设计：Cron 常驻守护、挂机自愈与对话流/抽屉双向交互式任务卡片

- **设计日期**：2026-10-03
- **状态**：已呈批 (Approved)
- **自治等级**：DRAFT (AP-05)
- **归属规范**：ADR-0268 落地深化、AP-01 负向边界、AP-02 测试不变量

---

## 1. 背景与核心问题

在 ADR-0268（Cron 地基）落地后，系统具备了领域层 `CronStore`、`CronService`、`next_run` 纯函数算法以及模型认知工具 `cron.add/list/view`，并在前端预备了初步的「即将到来」抽屉。然而在端到端闭环中存在两大断点：
1. **触发层断路（未常驻）**：生产环境中未接入常驻定时 Tick 循环，导致时间到了无法自动触发提醒与自主任务；若服务器关机或休眠，错过的任务缺乏系统性自愈与防轰炸补偿机制。
2. **体验层单向与断裂**：触发后缺乏强触达交互，仅靠冷文本容易遗漏；右侧栏「即将到来」缺乏编辑与删除等全能管控；会话内缺乏**原生交互式任务卡片**（无法直接在聊天界面推迟、编辑或删除）。

本设计旨在彻底打通**后端常驻守护与挂机自愈**、**会话原生交互式任务卡片（In-Chat Task Card）**与**右侧栏「即将到来」双向强联动**。

---

## 2. 架构设计与系统分层 (DDD)

### 2.1 系统分层
```
contracts (CronJob, CronRun, ReminderDeliveryPayload, DeliveryTarget)
   ↓
domain / infrastructure (CronStore, CronService, CronScheduler, CronDaemonService)
   ↓
application / kernel boot (Lifespan Hook, Ticker Loop, WorkerRunner, SessionStore)
   ↓
transport / webserver (REST /v1/assistants/{id}/jobs CRUD & WebSocket Broadcast)
   ↓
presentation (LobeHub UI: Interactive Task Card, Upcoming Drawer, Web Notifications)
```

1. **契约层 (`lca/contracts/models/cron/`)**：
   - 固化 `CronTaskCardWidgetPayload` 契约，支持定义：`job_id`、`title`、`body`、`schedule_label`、`next_run_local`、`execution_kind`、`due`、`enabled`、`delayed_by_seconds` 及可用 actions（`snooze`、`edit`、`delete`、`toggle_pause`）。
2. **基础设施与内核常驻 (`lca_kernel/boot/lifespan.py` & `lca/infrastructure/cron/`)**：
   - 在 Starlette Lifespan 中注入 `CronDaemonService`，启动高精度后台轮询协程（默认 15s tick）。
   - 采用文件锁 `cron.lock` 守护单实例，崩溃自动收割。
3. **执行与投递闭环 (`CronWorkerRunner`)**：
   - 当任务 `due=True`：
     - 若为提醒或指令，构造交互式任务卡片，通过 `SessionStore.append` 向会话追加携带 `[widget:cron_task_card]` 结构化标签的助理消息。
     - 同时通过 WebSocket 广播实时事件，通知前端激活桌面 Notification。
     - 在 `cron/{job_id}/runs/` 落盘 `CronRun` 记录。
4. **前端交互层 (`deploy/lobehub/patches/ui/`)**：
   - **对话流交互式卡片 (`CronTaskCard.tsx`)**：醒目闹钟微光徽标、正文展示、时间戳、快捷推迟胶囊（`+10m`、`+30m`、`+1h`）、原地编辑与删除。
   - **右侧栏全能抽屉 (`CronUpcomingPanel.tsx`)**：状态 Tag、倒计时指示、立即触发按钮、启停 Switch、顶级全能编辑/创建弹窗（支持预设与 Cron 表达式可视化）、删除二次确认。
   - **双向数据同步**：会话操作即时同步右侧栏，抽屉编辑即时更新卡片，数据源唯一（SSOT: 后端 REST 接口）。

---

## 3. 挂机与重启自愈算法 (Missed Run Policy)

在内核启动后的首轮 Tick 中，对历史到期任务执行智能补偿判定：
1. **一次性任务 (Oneshot)**：
   - 若关机期间到达时间且尚未有成功 `CronRun` 记录：
   - 立即执行补发，并在交付卡片中计算并注明 `delayed_by_seconds`（如“延迟送达：关机补偿，原定时间 21:14”），保证关键提醒绝对不丢。
2. **周期性任务 (Cron / Interval)**：
   - 严格执行**防轰炸机制**：即使关机期间错过了多次触发，绝不连续触发多次。
   - 调度器以当前开机时间为基准，对齐到**下一个未来的周期时间点**，确保任务接续运行且不干扰用户。

---

## 4. 边界清单 (AP-01)

### Owns (本方案负责范围)
1. `lca_kernel/boot/lifespan.py` 中装配常驻 `CronDaemonService` 及其启动/关停生命周期。
2. `lca/infrastructure/cron/daemon.py` 常驻 Tick 调度器与挂机补偿机制。
3. `CronWorkerRunner` 落地：通过 `SessionStore.append` 向会话追加结构化卡片消息。
4. 前端交互式任务卡片 `CronTaskCard.tsx`（含快捷 Snooze、原地编辑、删除、状态切换）。
5. 升级前端 `CronUpcomingPanel.tsx`（全能编辑弹窗、立即执行、启停 Switch、删除确认）。
6. 全量自动化不变量测试（INV-CRON-01 至 INV-CRON-06）。

### Does NOT own (严格禁止修改范围)
1. 严禁改动 LCA 核心认知图节点（Think/Gate/Act 闭集不变）。
2. 严禁修改或绕过已有的 `SessionStore` 会话真值体系，不建立平行消息存储。
3. 严禁在本仓提交任何非 LCA 框架的外部资产或宿主机运维脚本。

---

## 5. 核心测试不变量矩阵 (AP-02)

| 不变量 ID | 验证维度 | 判定准则 |
|---|---|---|
| **INV-CRON-01** | 常驻存活与生命周期 | 内核启动后后台协程保持 running；关机时优雅释放 `cron.lock` 无孤儿协程。 |
| **INV-CRON-02** | 到点自动触发与落盘 | Mock 时钟超过 `at` 后，单次 Tick 必须产出 `started=1`，且对应 `job/runs/` 必须落盘新 `CronRun`。 |
| **INV-CRON-03** | 关机智能补偿 | 关机错过时段后，oneshot 任务首轮 Tick 补发且携带 `delayed_by_seconds`；周期性任务下次执行时间必须严格大于当前墙钟时间。 |
| **INV-CRON-04** | 会话卡片契约规范 | 投递消息必须包含合法的 `[widget:cron_task_card]` 结构化 JSON 载荷，必含 `job_id`、`title`、`schedule`。 |
| **INV-CRON-05** | REST 接口编辑与删除 | `PUT` 更新时间后 `next_run_local` 与服务端计算一致；`DELETE` 后该任务彻底物理移除。 |
| **INV-CRON-06** | 快捷推迟 (Snooze) 幂等 | 点击 `+10m` 后，生成延后 10 分钟的新任务或重锚定任务，时间计算精确到秒。 |
