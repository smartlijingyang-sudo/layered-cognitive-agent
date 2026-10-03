# Cron 常驻守护、挂机自愈与对话流/抽屉双向交互式任务卡片实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 落地 Cron 后端常驻守护（随 Kernel Lifespan 自启、文件锁防重、挂机开机智能补偿）、真实会话消息投递（含会话内原生交互式任务卡片 `CronTaskCard`）以及前端右侧栏「即将到来」全能顶级交互（编辑、删除、推迟、启停 Switch、立即触发）。

**Architecture:** 严格遵循 LCA DDD 分层模型，契约层定义 `CronTaskCardWidgetPayload`；基础设施层实现 `CronDaemonService` 随 `lca_kernel` ASGI Lifespan 常驻，驱动 `CronScheduler.tick()`；到期任务经 `CronWorkerRunner` 直接写入 `SessionStore` 会话流生成 `[widget:cron_task_card]`；前端 LobeHub UI 挂载原生卡片与全能抽屉，实现会话与抽屉的双向秒级联动。

**Tech Stack:** Python 3.11+, Pydantic v2, Starlette Lifespan, asyncio, React, Ant Design, antd-style, TypeScript.

---

### Task 1: 契约层扩展与交互式任务卡片 Payload (`CronTaskCardWidgetPayload`)

**Files:**
- Create: `lca/contracts/models/cron/card.py`
- Modify: `lca/contracts/models/cron/__init__.py`
- Test: `tests/contracts/cron/test_task_card_payload.py`
- Does NOT own: `lca/cognition/`, `lca/domain/`, 前端代码 (AP-01)
- Invariants to test: `CronTaskCardWidgetPayload` 严格遵循 Pydantic frozen 契约，字段必含 `job_id`, `title`, `body`, `schedule_label`, `next_run_local`, `execution_kind`, `delayed_by_seconds`, `actions` (AP-02)

**Step 1: Write the failing test**
创建 `tests/contracts/cron/test_task_card_payload.py`，验证 `CronTaskCardWidgetPayload` 序列化与反序列化、合法 actions 与只读冻结特性。

**Step 2: Run test to verify it fails**
运行: `pytest tests/contracts/cron/test_task_card_payload.py -v`
预期: FAIL with ImportError

**Step 3: Write minimal implementation**
创建 `lca/contracts/models/cron/card.py`，实现 `CronTaskCardAction` 枚举与 `CronTaskCardWidgetPayload` 模型，并在 `__init__.py` 导出。

**Step 4: Run test to verify it passes**
运行: `pytest tests/contracts/cron/test_task_card_payload.py -v`
预期: PASS

**Step 5: Commit**
```bash
git add lca/contracts/models/cron/ tests/contracts/cron/
git commit -m "feat(cron): add CronTaskCardWidgetPayload contract for in-chat interactive task cards"
```

---

### Task 2: 挂机自愈调度器与 Worker 投递执行器 (`CronDaemonService` & `CronWorkerRunner`)

**Files:**
- Create: `lca/infrastructure/cron/worker_runner.py`
- Create: `lca/infrastructure/cron/daemon.py`
- Test: `tests/infrastructure/cron/test_daemon_self_healing.py`
- Does NOT own: `lca/cognition/`, 前端组件 (AP-01)
- Invariants to test:
  - INV-CRON-01 (生命周期 start/stop 优雅释放锁)
  - INV-CRON-02 (到期 Tick 自动触发并在 `job/runs/` 落盘 `CronRun`)
  - INV-CRON-03 (关机补偿：oneshot 补发带 `delayed_by_seconds`，周期性任务平滑对齐未来执行点)
  - INV-CRON-04 (向 `SessionStore` 写入 `[widget:cron_task_card]` 结构化消息)

**Step 1: Write the failing test**
创建 `tests/infrastructure/cron/test_daemon_self_healing.py`，测试调度守护在真实 Store 下的心跳触发、关机补偿逻辑与 Worker 投递。

**Step 2: Run test to verify it fails**
运行: `pytest tests/infrastructure/cron/test_daemon_self_healing.py -v`
预期: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**
实现 `CronWorkerRunner`（负责构建任务卡片并追加至 Session）与 `CronDaemonService`（常驻循环、15s tick、挂机启动首轮补偿扫描）。

**Step 4: Run test to verify it passes**
运行: `pytest tests/infrastructure/cron/test_daemon_self_healing.py -v`
预期: PASS

**Step 5: Commit**
```bash
git add lca/infrastructure/cron/ tests/infrastructure/cron/
git commit -m "feat(cron): implement CronDaemonService with self-healing and CronWorkerRunner"
```

---

### Task 3: 内核 Lifespan 挂载常驻守护 (`lca_kernel/boot/lifespan.py`)

**Files:**
- Modify: `lca_kernel/boot/lifespan.py`
- Test: `tests/boot/test_cron_lifespan_integration.py`
- Does NOT own: 路由逻辑, 认知图 (AP-01)
- Invariants to test: 内核启动自动启动 `CronDaemonService`，进程退出触发 shutdown 时优雅停止协程并释放锁。

**Step 1: Write the failing test**
创建 `tests/boot/test_cron_lifespan_integration.py`，模拟 ASGI lifespan startup 与 shutdown，断言 daemon 正常启动且未阻断主服务。

**Step 2: Run test to verify it fails**
运行: `pytest tests/boot/test_cron_lifespan_integration.py -v`
预期: FAIL

**Step 3: Write minimal implementation**
在 `lca_kernel/boot/lifespan.py` 的 lifespan context 中初始化并挂载 `CronDaemonService`。

**Step 4: Run test to verify it passes**
运行: `pytest tests/boot/test_cron_lifespan_integration.py -v`
预期: PASS

**Step 5: Commit**
```bash
git add lca_kernel/boot/lifespan.py tests/boot/test_cron_lifespan_integration.py
git commit -m "feat(kernel): wire CronDaemonService into Starlette lifespan"
```

---

### Task 4: REST API 增强（立即触发 Run Now 与 Snooze 推迟端点）

**Files:**
- Modify: `lca/plugins/transport/webserver/routes_1/routes_assistants/jobs.py`
- Test: `tests/lca_plugins/transport/webserver/test_jobs_endpoints_actions.py`
- Does NOT own: 前端代码 (AP-01)
- Invariants to test:
  - POST `/v1/assistants/{id}/jobs/{job_id}/run` 支持立即手动触发并返回 run 摘要
  - POST `/v1/assistants/{id}/jobs/{job_id}/snooze` 支持快捷推迟 N 分钟（默认 10m）并原子重写 `next_run`

**Step 1: Write the failing test**
创建 `tests/lca_plugins/transport/webserver/test_jobs_endpoints_actions.py`，验证 `/run` 与 `/snooze` 端点行为与错误校验。

**Step 2: Run test to verify it fails**
运行: `pytest tests/lca_plugins/transport/webserver/test_jobs_endpoints_actions.py -v`
预期: FAIL with 404 / 405

**Step 3: Write minimal implementation**
在 `jobs.py` 中增加 `/jobs/{job_id}/run` 与 `/jobs/{job_id}/snooze` 路由及处理函数。

**Step 4: Run test to verify it passes**
运行: `pytest tests/lca_plugins/transport/webserver/test_jobs_endpoints_actions.py -v`
预期: PASS

**Step 5: Commit**
```bash
git add lca/plugins/transport/webserver/routes_1/routes_assistants/jobs.py tests/lca_plugins/transport/webserver/
git commit -m "feat(routes): add /run and /snooze endpoints for cron jobs"
```

---

### Task 5: 前端对话流原生交互式任务卡片组件 (`CronTaskCard.tsx` + 渲染挂载)

**Files:**
- Create: `deploy/lobehub/patches/ui/CronTaskCard.tsx`
- Modify: `deploy/lobehub/patches/ui/cron_upcoming_panel.py`
- Test: `tests/patches/ui/test_cron_task_card_patch.py`
- Does NOT own: 后端调度器 (AP-01)
- Invariants to test: 前端正确识别 `[widget:cron_task_card]` 标签，渲染高保真任务卡片，支持原地推迟（+10m/+30m/+1h）、原地打开编辑弹窗、原地删除 Popconfirm 确认。

**Step 1: Write the failing test**
创建 `tests/patches/ui/test_cron_task_card_patch.py`，校验补丁文件存在性、组件语法与 patch 注册。

**Step 2: Run test to verify it fails**
运行: `pytest tests/patches/ui/test_cron_task_card_patch.py -v`
预期: FAIL

**Step 3: Write minimal implementation**
创建 `CronTaskCard.tsx`，实现现代磨砂玻璃质感、闹钟微光呼吸动效、快捷推迟胶囊、原地编辑弹窗联动与删除气泡确认；在 `cron_upcoming_panel.py` 注册安装。

**Step 4: Run test to verify it passes**
运行: `pytest tests/patches/ui/test_cron_task_card_patch.py -v`
预期: PASS

**Step 5: Commit**
```bash
git add deploy/lobehub/patches/ui/ tests/patches/ui/
git commit -m "feat(ui): add interactive in-chat CronTaskCard component"
```

---

### Task 6: 前端右侧栏「即将到来」抽屉顶级交互升级 (`CronUpcomingPanel.tsx`)

**Files:**
- Modify: `deploy/lobehub/patches/ui/CronUpcomingPanel.tsx`
- Modify: `deploy/lobehub/patches/ui/cron_upcoming_panel.py`
- Test: `tests/patches/ui/test_cron_upcoming_panel_patch.py`
- Does NOT own: 后端调度器 (AP-01)
- Invariants to test: 支持启停 Switch、手动立即执行（Run Now）、全能编辑/创建弹窗（日期时间选择器 + 周期可视化配置）、删除 Popconfirm 确认，并保持与会话卡片双向 SWR 联动。

**Step 1: Write the failing test**
创建 `tests/patches/ui/test_cron_upcoming_panel_patch.py`，验证面板代码包含编辑弹窗、立即执行、删除按钮与启停开关。

**Step 2: Run test to verify it fails**
运行: `pytest tests/patches/ui/test_cron_upcoming_panel_patch.py -v`
预期: FAIL

**Step 3: Write minimal implementation**
全面升级 `CronUpcomingPanel.tsx`：增加顶部「+ 新建任务」与倒计时统计卡、卡片快捷操作（立即执行、编辑、删除、启停）、高级编辑/创建弹窗（可视化时间与 Cron 表达式生成）、SWR 自动轮询同步。

**Step 4: Run test to verify it passes**
运行: `pytest tests/patches/ui/test_cron_upcoming_panel_patch.py -v`
预期: PASS

**Step 5: Commit**
```bash
git add deploy/lobehub/patches/ui/CronUpcomingPanel.tsx deploy/lobehub/patches/ui/cron_upcoming_panel.py tests/patches/ui/
git commit -m "feat(ui): upgrade CronUpcomingPanel with full-featured edit, delete, run-now and status switches"
```

---

### Task 7: 全链路端到端集成验证与门禁体检 (INV-CRON-01 ~ INV-CRON-06)

**Files:**
- Create: `tests/scenario/test_cron_full_lifecycle_invariants.py`
- Does NOT own: 生产业务逻辑 (AP-01)
- Invariants to test: 完整回归 INV-CRON-01 至 INV-CRON-06 矩阵，确保关机智能补偿、到期自动落盘、会话卡片注入、REST 接口操作完全一致。

**Step 1: Write end-to-end invariant test**
创建 `tests/scenario/test_cron_full_lifecycle_invariants.py`，模拟系统开机、到期触发、会话写入、REST 编辑、删除与推迟全生命周期。

**Step 2: Run all cron-related tests**
运行: `pytest tests/contracts/cron tests/infrastructure/cron tests/boot tests/lca_plugins/transport/webserver tests/patches/ui tests/scenario/test_cron_full_lifecycle_invariants.py -v`
预期: 全数 PASS

**Step 3: Check code quality and formatting**
运行: `ruff check lca/contracts/models/cron lca/infrastructure/cron lca_kernel/boot lca/plugins/transport/webserver deploy/lobehub/patches/ui tests/`
运行: `ruff format --check lca/ tests/ deploy/`
运行: `git diff --check`
预期: 0 报错，无多余未暂存改动。

**Step 4: Commit**
```bash
git add tests/scenario/test_cron_full_lifecycle_invariants.py
git commit -m "test(cron): add full lifecycle integration test covering INV-CRON-01 to INV-CRON-06"
```
