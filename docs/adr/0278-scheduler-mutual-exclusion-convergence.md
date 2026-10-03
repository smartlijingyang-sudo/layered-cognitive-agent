# ADR-0278：双调度器互斥与自愈契约收敛（routine scheduler ↔ cron daemon）

## 状态

**Proposed — 2026-10-03**

> **一句话**：仓库现在有两个调度子系统（ADR-0263 的 routine scheduler 与 ADR-0268 深化的 cron daemon），它们独立实现了同一套"文件锁互斥 + stale 自愈"语义；本 ADR 把重合处钉成共享契约，把分岔处（失败处理语义）显式记录为待拍板项，不擅自统一。

## 0. 接任务前 7 问（精简自检）

1. 谁受益？两个调度赛道的维护者与李超：同一语义两处实现，drift 时有一份契约可对。
2. 真实问题？**同一互斥语义两份独立实现**：`lca/application/routine/locks.py:48` 的 `RoutineFileLock` 与 `lca/infrastructure/cron/scheduler.py:290-322` 的 `_acquire_lock`，逻辑实质相同但无共享原语、无设计文档交叉引用（cron design doc 对 0263 零引用，grep 实证）。
3. 删掉会坏什么？不坏——本 ADR 是收敛记录，不新增行为；但两份锁实现会继续无声 drift（stale 公式改一边、另一边不知道）。
4. 更简单方案？只在 backlog 记一笔。否决：互斥+自愈是生产正确性契约（双实例同跑会重复触发用户提醒），值得 ADR 级钉住。
5. 契约先行？是——语义已在两处落地，本 ADR 只做"名实相符"的收敛记录。
6. 与现有 ADR 冲突？无。0263 的裁决（文件锁 / stale=2×interval / 上限 90min，李超 `132f381a8`）被 cron 赛道逐字复现（代码注释引用 "ADR-0263 §9①②"），本 ADR 是收敛注记不是改判。
7. 状态诚实？Proposed。锁原语是否抽取、失败语义是否统一，全部待拍板，见 §3。

## 1. 实证

### 1.1 两处实现的语义同一性（2026-10-03 实测 main@1414f7e80）

| 维度 | routine 赛道（0263） | cron 赛道（0268 深化） |
|---|---|---|
| 锁介质 | 文件锁 `RoutineFileLock`（`lca/application/routine/locks.py:48`） | 文件锁 `cron.lock`（`lca/infrastructure/cron/scheduler.py:293`） |
| owner 标识 | hostname:pid（0263 C1 裁决） | `f"{socket.gethostname()}:{os.getpid()}"`（scheduler.py:297） |
| stale 公式 | ADR-0263:100 "stale 阈值：默认 2×routine interval，可配；绝对上限 90 分钟" | `stale_after_s = min(self._default_interval_s * 2.0, STALE_ABSOLUTE_CAP_S)`，`STALE_ABSOLUTE_CAP_S = 90 * 60`（scheduler.py:43, 311） |
| 收割留痕 | stale 收割发事件（0263 C2） | `_log.warning("cron.lock_stale_reaped owner=%s age_s=%d", …)`（scheduler.py:312-316） |

- 代码注释实锤引用：scheduler.py:290 `# ---- 文件锁（ADR-0263 §9①②，与 ProactiveScheduler 同模式） ----`
- **反向缺口**：`docs/plans/2026-10-03-cron-daemon-and-interactive-ui-design.md` 与 `-plan.md` 对 "0263"/"routine" **零引用**（grep 实证）——实现者知道 0263（代码注释），设计文档不知道，信息差真实存在。

### 1.2 失败语义的分岔（已实证，未裁决）

- routine 赛道：0263 C5 = 失败重试 3 次 + 死信 7 天（tick 驱动落 carrier 内）。
- cron 赛道：missed-run 补偿语义（design doc §3）——oneshot 关机期间到期→补发一次并注明 `delayed_by_seconds`（`lca/infrastructure/cron/worker_runner.py:92-144` 落盘）；periodic→永不连续补发多次，对齐下一个未来周期点（防轰炸）。
- `worker_runner.py` 内 retry/dead-letter **零命中**（grep 实证）——cron job 执行失败无重试语义。
- 两条失败处理路径并存，文档上无"刻意分岔"声明——是设计如此还是遗漏，未知，见待拍板③。

## 2. 契约

- **C1（共享互斥语义，两处已落地）**：调度器单实例互斥 = 文件锁 + owner(hostname:pid) + mtime 心跳 + stale=2×interval（绝对上限 90min）+ 收割留事件/日志。任一赛道改公式必须同步另一赛道，或走待拍板①的抽取方案。
- **C2（域边界，现状描述）**：routine scheduler 管内部 interval 例程；cron daemon 管用户 cron jobs/reminders。锁文件与目录相互独立（`cron.lock` vs routine 锁），两赛道不互斥、不共享 tick——**分开是刻意**，不是事故。
- **C3（missed-run 补偿，cron 赛道已落地）**：oneshot 错过→补发一次 + `delayed_by_seconds` 注明延迟；periodic 错过→只对齐下一个未来周期点，绝不连续补发。由 INV-CRON-03 钉住（`tests/scenario/test_cron_full_lifecycle_invariants.py`），本 ADR 只做引用不重复钉。
- **C4（失败语义分岔，现状，未裁决）**：routine 赛道走重试+死信；cron 赛道走补偿、无重试。本条只记录分岔事实，不裁决哪边对——见待拍板③。

## 3. 待拍板（需李超/Athena 裁决，arch 轮不擅自决定）

1. 锁原语要不要抽成共享实现？两处 `_acquire_lock` 逻辑实质相同，长期 drift 风险真实；但抽取要跨 `lca/application` 与 `lca/infrastructure` 层，YAGNI 反对。
2. ADR-0263 Proposed→Accepted 时，cron daemon 是否计为第二条落地证据链？（0263 的 T1–T5 验收是 routine 赛道的；cron 赛道有 INV-CRON-01~06 全绿。）
3. cron job 执行失败要不要 0263 C5 式的重试+死信？当前零重试——提醒类任务"失败补发"可能本就无意义（用户已看到过期提醒），也可能是遗漏。
4. design doc / plan doc 要不要补一行对 0263 的交叉引用？（非 ADR 化，只是引用；设计文档与实现注释的信息差已实锤。）

## 4. 验收

- T1：双锁语义一致性——任一赛道改 stale 公式/锁文件名，另一赛道的契约测试变红（或走待拍板①抽取后改为单点钉）。
- T2：`cron.lock` stale 收割断言——写过期锁文件 → `_acquire_lock` 收割 → `cron.lock_stale_reaped` 日志/事件。
- T3：missed-run 两类任务行为钉——已由 INV-CRON-03 覆盖，本 ADR 只做引用。
- T4：待拍板③④决议落盘——任一方向都行，但必须显式记录，不能 silent。

## 5. 决策记录

（空，待裁决。）
