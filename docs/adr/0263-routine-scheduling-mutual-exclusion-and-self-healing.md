# ADR-0263 — 例程调度互斥与自愈契约：单实例互斥、锁超时自愈、SKIP 可观测

## 状态

**Proposed — 2026-10-02**

> **一句话**：生产 Muse 调度模式（锁目录 + mtime 心跳 + stale 收割 + busy→SKIP 跳过）的 LCA 落地提案。`RoutineSchedulerService`（ADR-0248 §3.4/s04）只有触发判定 + 预算闸，缺五条契约：① 同一 routine 单实例互斥；② 锁超时自愈（持锁崩溃不饿死后来者）；③ busy→显式 SKIP（可观测的跳过 verdict，不静默）；④ 触发记录持久化（重启不丢）；⑤ 单 routine 失败不杀 tick 循环。

**Extends**：
- [ADR-0248](./0248-grok-bot-coordinator-runtime-evidence.md)（Grok Bot coordinator runtime evidence）：§3.4/s04 例程编排的证据级设计——本 ADR 补它的生产缺口：0248 只规定了"何时触发"，没规定"触发时已有实例在跑怎么办、锁死了怎么办、重启后怎么办"；
- 生产 Muse 调度契约（可观测活实例：iter-arch / iter-tests / iter-quality 三路 cron 的开工锁段）：锁目录 + `age < 阈值 → busy → skip` + stale 收割 + 持有锁至轮次结束 + 释放——本 ADR 把这套模式契约化为 LCA 的 routine 调度语义。

**实证来源**：2026-10-02 iter-arch 轮对当前实现的实证审计——
- 已落地一（触发判定）：`lca/application/routine/scheduler.py::RoutineSchedulerService`——`can_trigger` 查 spec 存在 + enabled + `SpendGuard.is_budget_exceeded`（INV-08）；`get_run_params` 组装 run 参数（assistant_id / prompt / `WakeSource.ROUTINE` / 预算 / extra.routine_id）；
- 已落地二（合法沉默）：`create_wake_source` 注入 `WakeSource.ROUTINE`，天然具备 INV-07 合法沉默放行特权；
- 缺口一（**无互斥**）：`can_trigger` 只看 enabled + 预算，**不看"是否已有实例在跑"**——同一 routine 可被并发/重叠触发，两个 run 并行执行同一 prompt；
- 缺口二（**触发记录只在内存**）：`record_triggered` 写 `self._last_triggered: dict[str, int]`——进程重启即丢，重启后可能立即重复触发；
- 缺口三（**触发事件无 lifecycle**）：`RoutineTrigger`（`lca/contracts/models/routine/models.py:40`，frozen，`extra="forbid"`）只有 `routine_id` / `triggered_at_ms` / `trigger_source` 三字段——无状态机（排队中/运行中/完成/失败/跳过），触发之后发生了什么不可追踪；
- 缺口四（**生产无 tick 驱动**）：`lca/` 内 `can_trigger` / `record_triggered` / `get_run_params` 的引用只有 scheduler.py 自身——生产链路无 tick 调用方，调度器尚未接入生产（仅测试引用：`tests/application/routine/test_routine_scheduler_and_spend_guard.py`、`tests/scenario/adr0248/test_grok_bot_production_closed_loop.py`）；
- 缺口五（**触发失败无语义**）：`can_trigger` 返回 False 时调用方只能"不触发"——静默跳过还是可观测 SKIP、失败重试还是死信，全无规定。

---

## 0. 接任务前 7 问

1. **问题是什么？** ① 同一 routine 可被重叠触发（无互斥）；② `_last_triggered` 内存态重启丢失；③ `RoutineTrigger` 无 lifecycle，触发后不可追踪；④ 生产无 tick 驱动；⑤ 触发失败/跳过无可观测语义。
2. **受影响的事实或契约是什么？** routine 的并发安全、触发记录的持久性、触发事件的可观测性、tick 驱动的落点。
3. **唯一真值在哪里？** "某 routine 此刻是否在跑" = 互斥锁的持有状态，不是内存里的布尔值；"上次触发时间" = 持久化记录，不是进程内存。
4. **改变哪个边界？** 把"触发判定"从"时间到了 + 预算够"扩展为"时间到了 + 预算够 + 没人正在跑 + 上次触发已落盘"；把"跳过"从静默变成可观测 verdict；把"锁"从无变成带超时的自愈锁。
5. **现有 Protocol / ADR 能否表达？** 不能。ADR-0248 只给了触发判定的证据级设计；SpendGuard（INV-08）是预算闸，不是并发闸。
6. **失败、重试、恢复和幂等语义是什么？** 持锁崩溃是预期场景（stale 收割自愈）；busy 触发返回 SKIP（不排队）；单 routine 失败不杀 tick（失败隔离）；`record_triggered` 幂等（同 routine_id 同触发窗口去重）。
7. **如何验证？** §6 的 5 条验收用例。

---

## 1. C1 — 同一 routine 单实例互斥

触发执行前必须取得以 `routine_id` 为键的互斥锁；锁带 owner 标识（routine_id + 持有者身份）与心跳（mtime/心跳时间戳）。
未取得锁的触发直接走 C3 的 SKIP（`ALREADY_RUNNING`），不排队、不等待。

## 2. C2 — 锁超时自愈

锁带 stale 阈值（可配；默认建议为该 routine interval 的倍数，具体倍数待拍板）：
- 持锁者心跳超时 → 锁被收割，新触发可取得锁；
- 收割必须发布事件留痕（如 `routine.lock.stale_reclaimed.v1`，含 routine_id / 原 owner / 持有时长），**绝不静默**；
- 持锁崩溃是预期场景，不是异常路径——自愈是契约的一部分，不是运维补救。

## 3. C3 — busy → 显式 SKIP 语义

触发判定不满足时，返回可观测的 SKIP verdict，而不是静默 `False`：
- 原因枚举：`ALREADY_RUNNING`（互斥锁被占）/ `BUDGET_EXCEEDED`（SpendGuard 熔断）/ `NOT_DUE`（未到触发时间）/ `DISABLED`（routine 未启用）；
- 每次 SKIP 写 journal/spine 留痕（含 routine_id / 原因 / 判定时刻）——"为什么没跑"可查；
- SKIP 不重试、不排队：下一次 tick 重新判定。

## 4. C4 — 触发记录持久化

`_last_triggered` 从内存 dict 下沉为 repository 持久化：
- 进程重启后按持久化时间戳判定，不立即重复触发；
- `record_triggered` 幂等：同 routine_id 在同一触发窗口内重复记录去重。

## 5. C5 — 失败隔离

单个 routine 执行抛错：
- 不杀死 tick 循环——tick 继续处理下一个 routine；
- 失败计数进 repository，达阈值后按死信语义处理（重试次数 / 退避 / 死信保留，细节待拍板）；
- 失败事件留痕（含 routine_id / 错误摘要 / 已重试次数）。

---

## 6. 验收标准

- T1 并发触发：同时触发同一 routine 两次，第二次返回 `SKIP(ALREADY_RUNNING)`，全程只有一个执行实例；
- T2 锁自愈：持锁进程被 kill -9 后，stale 阈值过后新触发成功取得锁，并留有收割事件；
- T3 重启不丢：进程重启后 `_last_triggered` 仍有效，不立即重复触发；
- T4 预算闸：SpendGuard 熔断时触发判定返回 `SKIP(BUDGET_EXCEEDED)`（`can_trigger` 现有 false 语义升契约）；
- T5 失败隔离：单个 routine 执行抛错，tick 循环继续处理下一个 routine，无级联死亡。

---

## 7. 待拍板

1. **锁介质**：文件锁 vs repository 行锁 vs 分布式锁——单机 carrier 文件锁足够，多实例部署才需分布式；
2. **stale 阈值**：默认值与可配粒度（建议按 routine interval 倍数，如 2×interval，待定）；
3. **失败重试/死信语义**：重试次数、退避策略、死信保留时长；
4. **tick 驱动落点**：carrier 内 vs 独立 daemon（当前生产代码无 tick 驱动，先定落点再谈实现）。

---

## 8. 与现有机制的关系

- `SpendGuard`（INV-08）是**预算闸**，互斥锁是**并发闸**——两者正交，可叠加判定，顺序固定：enabled → 互斥锁 → SpendGuard → 时间窗口；
- `WakeSource.ROUTINE`（INV-07）合法沉默特权不变——C1–C5 只管"能不能跑"，不管"跑起来吵不吵"；
- `RoutineTrigger` 加 lifecycle 状态是 C3/C5 的前置——状态机设计（排队中/运行中/完成/失败/跳过）待实现 ADR 细化；`extra="forbid"` 的 frozen 模型需版本化演进。
