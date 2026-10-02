# ADR-0268 实施进度与交接（cron 地基已落地）

2026-10-02。本文件是给后续接手 agent 的交接说明。

## 已完成

分支 `feat/adr-0268-cron-foundation` 上已有 4 个提交，对应 ADR-0268 的地基：

1. `f79254e89` 契约模型与 `next_run` 纯函数
   - `lca/contracts/models/cron/models.py`：`CronJob`、五种 schedule、`NextFire`、`ScheduledHandoff`、`CronRun`、`CronListItem`、`CronValidationError`
   - `lca/domain/cron/next_run.py`：纯函数，时钟由调用方传入，DST 缺口用「转 UTC 再转回」检测，秋令时取 `fold=0`
   - 契约测试 `tests/contracts/cron/`、属性测试 `tests/domain/cron/test_next_run.py`
2. `072a1e801` 删除 `RoutineSpec.cron_expr` 与 `interval_seconds`（验收第 0 条）
   - `lca/contracts/models/routine/models.py` 及三个测试文件同步更新
3. `fa1ff0ebf` CronStore 与 worker 上下文
   - `lca/domain/cron/store.py`：`cron/<job_id>.json` 原子替换写，run 追加在 `cron/<job_id>/runs/`，删除定义不删 run
   - `lca/domain/cron/worker_context.py`：`assemble_worker_context(body, WorkerProductContext)`，参数没有父 transcript
   - 签名测试 `tests/domain/cron/test_worker_context.py` 钉住结构保证
4. `5be07b75a` CronService
   - `lca/domain/cron/service.py`：add_job（重复 id 不覆盖）、get_job、list_items（即将到来投影）、replace_job、remove_job
   - 投影只暴露 `CronListItem` 闭集，`next_run_local` 与墙钟一致，停用任务 due 强制为假，已完成 oneshot 不进列表，`last_delivery` 按 §10 汇总
   - 测试 `tests/domain/cron/test_service.py`

## 已完成（主体）

1. 结构保证（§14.1、§14.2）
   - `lca.nothing_to_do` 工具（`lca/infrastructure/tools/lca/`）已注册 `lca` 命名空间，用户轮 wire 过滤，用户轮调用回注错误
   - `next_run` 纯函数与 worker 上下文签名测试（地基阶段）
   - 模型改 schedule/timezone/`cron.remove` 走审批门：`decision_needs_approval` 对 `cron.update`/`cron.remove` 返回 True，工具执行前暂停，写函数不被调用
2. cron 工具插件（`lca/plugins/domain/tools/cron/plugin.py`）
   - `cron.add` 直接写（重复 id 不覆盖）；`cron.view` 全量定义 + run；`cron.list` 只暴露 `CronListItem` 闭集
   - `cron.update`/`cron.remove` 不调用写函数，返回审批提示；写由卡片路径 HTTP PUT/DELETE 完成
   - 已挂入 `bundles/assistant-runtime.yaml`
3. 调度器与 handoff 注入（`lca/infrastructure/cron/scheduler.py`）
   - 文件锁、心跳、stale 收割；重叠队列（superseded + not_sent）；超时重试
   - `surface/developer_message` 事件类型注入父轮（`RunSessionWriter.append_developer_message`）
   - §14.3 故障注入测试
4. HTTP jobs 路由（`routes_assistants/jobs.py`）
   - GET 列表投影、POST 创建（`chat_id` 作为 `created_chat_id`）、PUT 卡片更新（改 schedule/timezone 重写 `anchor_at`）、DELETE 删除定义
   - `:fire` 保持 501（CronJob 无 HTTP fire）
5. 前端「即将到来」tab（`deploy/lobehub/patches/ui/cron_upcoming_panel.py` + `CronUpcomingPanel.tsx`）

## 关键文件

- 契约：`lca/contracts/models/cron/`
- 领域：`lca/domain/cron/`（next_run、store、worker_context、service）
- 工具线：`lca/cognition/body/tools/tool_wire_gate.py`、`lca/infrastructure/tool_defer/session.py`
- 审批现状：`decision_needs_approval` 对 `cron.update`/`cron.remove` 返回 True，工具执行前经 `act.approve.gate` 暂停，写函数不被调用；写由卡片路径 HTTP PUT/DELETE 完成
- 工具注册参考：`lca/plugins/domain/tools/assistant_tools/plugin.py`、`lca/plugins/tools/file_write.py`
- 实施文件：`lca/plugins/domain/tools/cron/plugin.py`、`lca/infrastructure/tools/cron/`、`lca/infrastructure/cron/scheduler.py`、`routes_assistants/jobs.py`、`deploy/lobehub/patches/ui/cron_upcoming_panel.py`

## 验证命令

```bash
.venv/bin/pytest tests/contracts/cron tests/domain/cron tests/plugins/domain/tools/cron tests/infrastructure/cron tests/lca_plugins/transport/webserver tests/infrastructure/runtime_plane/access -q
.venv/bin/ruff check lca/contracts/models/cron lca/domain/cron lca/infrastructure/cron lca/infrastructure/tools/cron lca/plugins/domain/tools/cron tests/contracts/cron tests/domain/cron tests/infrastructure/cron tests/plugins/domain/tools/cron
```

## 注意事项

- `mypy` 四个 cron 路径退出 1 是既有失败：38 个错误都在 cron 包之外（parent `__init__` re-export 引入），cron 文件本身无错误。
- `lint-imports` 退出 1 是既有失败：`lca.infrastructure.cli.commands.kernel` 与 `events_delivery` 的 ignored import 没有匹配。
- `check_package_contracts.py` 有 47 个既有失败（旧包），新增 cron 包未引入新失败。
- `tests/architecture/test_assistant_evolve_jobs_invariants.py` 有 4 个既有失败，因为它扫描 `lca/plugins/assistant/jobs.py`，该路径不存在。
- `tests/architecture/test_session_lifecycle_producers.py[approval.resolved.v1]` 与 `tests/plugins/session/test_runtime.py::test_plugin_manifest_metadata` 是既有失败，与 cron 实现无关。
- ADR-0268 §14.4 端到端周级探针尚未作为常驻测试落地。
- 工作区有并发会话的未提交文件（`event_translator.py`、`deploy/`、`docs/plans/task.md` 等），不要动、不要提交。
