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

## 未完成（按 ADR §14 验收顺序）

1. 结构保证剩余两条
   - `lca.nothing_to_do` 工具与「用户轮 wire 不暴露它」的过滤
   - 模型改 schedule/timezone/`cron.remove` 的审批回注：写函数在审批结果回注前不调用
2. cron 工具插件（`cron.add/view/update/remove/list`）注册到 `cron` 命名空间
   - 参考 `lca/plugins/domain/tools/assistant_tools/plugin.py` 的工厂模式与 `current_assistant_id()`
   - 需要解决 assistant home 路径注入与 `created_chat_id` 获取
3. 调度器 tick（重叠队列、超时重试、stale 收割）与 handoff 注入
4. HTTP jobs 路由替换 501（`lca/plugins/transport/webserver/routes_1/routes_assistants/jobs.py`）
5. 前端「即将到来」tab（`deploy/lobehub/patches`）

## 关键文件

- 契约：`lca/contracts/models/cron/`
- 领域：`lca/domain/cron/`（next_run、store、worker_context、service）
- 工具线：`lca/cognition/body/tools/tool_wire_gate.py`、`lca/infrastructure/tool_defer/session.py`
- 审批现状：探索报告确认现有 HITL 在审批后不会自动继续调用写函数，`cron.update` 需要新机制
- 工具注册参考：`lca/plugins/domain/tools/assistant_tools/plugin.py`、`lca/plugins/tools/file_write.py`

## 验证命令

```bash
.venv/bin/pytest tests/contracts/cron tests/domain/cron -q
.venv/bin/ruff check lca/contracts/models/cron lca/domain/cron tests/contracts/cron tests/domain/cron
.venv/bin/ruff format --check lca/contracts/models/cron lca/domain/cron tests/contracts/cron tests/domain/cron
.venv/bin/mypy lca/contracts/models/cron lca/domain/cron tests/contracts/cron tests/domain/cron
.venv/bin/lint-imports
```

## 注意事项

- `check_package_contracts.py` 有 47 个既有失败（旧包），新增 cron 包未引入新失败。
- `tests/architecture/test_assistant_evolve_jobs_invariants.py` 有 4 个既有失败，因为它扫描 `lca/plugins/assistant/jobs.py`，该路径不存在。
- 工作区有并发会话的未提交文件（`event_translator.py`、`deploy/`、`docs/plans/task.md` 等），不要动、不要提交。