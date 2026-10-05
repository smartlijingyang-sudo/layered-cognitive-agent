# ADR-0287: 语义记忆在线单写者与离线对账归位

> **Status: Proposed**（2026-10-04 起草）
> 本提案把李超的 note《语义记忆在线单写者与离线对账归位》（`docs/notes/proposed/seam/2026-10-04-semantic-memory-single-online-writer.md`）转成 ADR 契约提案。Note 本身已把两项跨 ADR 的依赖标注为"升级待裁决"，本 ADR 是提案承载体，**未落地任何代码，不改变任何现状**。

## 1. Context（发现）

语义记忆有两条在线写入路径，落在 respond 的两侧：`memory_add` / `memory_update` / `memory_remove`（act 相，产 typed Observation）与 `phase.reflect.memory.extract`（reflect 相 LLM 蒸馏）→ `phase.remember.write`（remember 相落盘，晚于本轮回复定稿）。`run_5eb9f012455e` 钉住时序：工具执行 13:42:23，`think.decision.parse` 定稿 13:42:26，`phase.remember.write` 落盘 13:42:43。

**F1（认领权跨轮泄漏，ADR-0260 C1 的 fail-open 缺口）。** ADR-0260 C1 要求"宣称已记下之前必须有写盘回执"；只有工具路径满足这个先后关系。但 `_project_curated` 对两条路径同等签发认领权（`assistant_memory.py:233`），remember 签发的那份当轮无人消费，落在 `{home}/memory/claim-latch.json`，被下一轮 `take_claim_right`（`assistant_memory.py:108`）读到——下一轮因此在没有任何写盘的情况下可以宣认已记下。`_LATCH_FILE = "claim-latch.json"`（`lca/infrastructure/memory/assistant_memory.py:67`）。认领权落盘还引入跨实例共享状态：`run_4fcfb6d83c8c` 中两个 `AssistantMemory` 实例对 latch 不同步导致错误拒绝。

**F2（对账三套实现，在线运行的是临时那套）。** `_append_semantic` 内联去重（在线唯一运行）/ `consolidate`（episode 折叠，仅 `lca-ops memory dream` 手动 CLI 可达）/ `LinkDecider.reconcile`（`consolidation.py:239`，运行时零引用）。内联去重无 NOOP 语义：136 行中 47 行退役态，89 个带 source 的事实维度中 17 个被两条路径各写一次。

**F3（ADR-0249 双轨 Accepted 但实现未接线）。** 0249 §0.1 要"毫秒级残差门控快记 + 夜晚离线固化双轨"；`phase.reflect.memory.extract` 仍是在线 LLM 蒸馏，`consolidation.py` 及其配套共 1066 行处于运行时零引用。

**F4（每日流水与 episode 缓冲的捕获缺口）。** `TrailWriter` 只被测试构造（`tests/infrastructure/memory/test_trail_append_only.py`、`tests/scenario/memory/test_adr0254_feature_matrix.py`），24 个助理 home 的 `memory/20*.md` 计数为 0，但 `run_dream` 经 `parse_trail` 读它、FTS 索引覆盖它，两个消费者对着一个无生产者的文件。

episode 侧的缺口不在开关而在模板。`phase.perceive.observe` 每轮无条件调 `record_task_episode`（`lca/nodes/perceive/observe/observe.py:62-67`，`913a967ae` 引入），真正的门是 `episode_home(runtime)` 能否解析（`lca/cognition/memory/daytime.py:17-31`）；`governor_enabled` 只控制 reflect 侧那一份与 perceive 近冗余的重复写入，两者对同一 `task` 与 `trace_id` 产出相同 `fact_id`。`govern()` 是三个闭合模板（`lca/cognition/memory/govern.py:21-25`），对「别那么啰嗦」「还是简洁一点好」返回 `None`，因为 verbosity 规则要求 `记住|以后` 合取（`govern.py:59`）；命中时又把 `explicit_user_authority` 硬编码为 `False`（`govern.py:59-67`），因此走不到 `_lifecycle` 的首次即提升分支（`lca/contracts/models/memory/episode.py:74-82`），必须凑够 `recurrence >= 2` 个不同 trace。唯一能给偏好首次提升的是 trail 路径，`_trail_episode` 在 `is_preference_statement` 命中时设 `authority=True`（`dream.py:137-158`），该正则为 `偏好|以后|不要|必须|记住|严禁|回复要|请记`（`contextfiles/domain/trail.py:18`），比 `govern()` 宽，而它没有写入方。

实测佐证。证据助理 `asst_ce7fecd65188` 跑的就是 `profiles/web-assistant.yaml`（活内核命令行确认），`governor_enabled` 为 true（`web-assistant.yaml:99`），`memory/episodes/` 仍为空，因为其三轮用户陈述「i am lee」「上海啊」「我有女儿 儿子 老婆 一家四口」不匹配任何模板。全库 524 个助理 home 中 5 个有 `memory/episodes/`，共 6 个文件，全部是 `residual: instruction` 的 `identity:role` 或 `identity:name`，`preference:verbosity`、`correction`、`error` 各为 0。`run_dream` 在生产从未运行过，任何 `semantic.json` 中都没有 `metadata.source == "dream"` 的记录。

附带的在产数据污染，已于 2026-10-05 单独修复（commit `487a9fdff`）。`_ROLE` 与 `_NAME` 用贪婪 `(.+)` 捕获到行尾，把一整句多事实陈述折进一条身份记录，并连同 `authority=True` 提升，违反 `govern()` 模块自述的「至多一条事实」。`_clean_capture` 的 40 字符截断不是成因，该记录的捕获串为 31 字符，未触线。修复把捕获边界收在子句标点，顿号仍留在边界内，回归测试 `tests/cognition/memory/test_govern_capture_boundary.py` 重放生产原句 `我叫老李,做架构设计,偏好 Python,回复请简短。写进你的长期记忆。` 并断言被折进的子句不出现在记录里。存量污染记录仍在 `asst_5166b058964f/memory/episodes/ep_dc6df2f81fd6d9e3.json`，属助理数据、不在本仓范围，清理需另行授权。

**F5（守卫 remedy 与判定不可判定性不匹配）。** `_CLAIM`（`acknowledgement.py:16`）用正则判定宣称，命中即整条替换回复。`run_3a523914cc0a` 的条件式能力提议（"我可以帮你记下来"）命中，本轮无写盘，用户收到 `_REFUSAL`。ADR-0260 §6.1 只把 fail-closed 用于精确可判定处。

## 2. Decision（提案，待裁决）

**D1（在线单写者）。** `memory_add` / `memory_update` / `memory_remove` 是语义记忆唯一的在线写者；`phase.reflect.memory.extract` 的 LLM 蒸馏移入 `run_dream`，在线保留毫秒级残差门控（`SalienceGate`、`filter_ingestion_modality`、`EpisodeBuffer`），即 ADR-0249 的 Fast Path。

**D2（认领权改派生读，latch 退役）。** 认领权来源改为本 run journal 中 memory 工具 Observation 的派生读，轮次边界为 `run_id`（会话投影一个文件 6 轮 6 run_id、ResumeCursor 的 session_seq 与 run cursor 双轴——按会话派生不可用）。`claim-latch.json` 及其读写路径、`take_claim_right`、`last_curated_receipt` setter 的 latch 副作用退役。"一次写盘至多支撑一次用户可见宣称"由轮次作用域保证。**硬前置：ADR-0260 §3 把"不改 take_claim_right 的消费语义"列为非目标（0260:78-81），退役前必须先有 ADR 裁决（修订 0260 或新开），不得随实施 PR 顺手退役。**

**D3（对账收敛到单一具名闸）。** ADD / UPDATE / DELETE / NOOP 四操作，重复输入产 NOOP 而不是退役旧行；`_append_semantic` 内联去重与未中选的实现退役。**硬前置：ADR-0277 待拍板⑥/⑦（typed 对象与 SemanticClaim 承载体）先行裁决。**

**D4（守卫 remedy）。** `_CLAIM` 命中且本轮无写盘证据时，经 act→think re-ask 边重写一轮（受已有 re-ask 硬上限约束，触顶才落 `_REFUSAL`）；`_CLAIM` 收窄排除条件式能力提议并补反向回归测试。`think.decision.repair` 不承担此职责（其范围是 tool-call 参数的确定性 schema 修复）。

**D5（交付门禁）。** Phase 0 离线轨可承接（dream 调度落地跑稳 + 目标 profile 有真实写入的在线残差捕获路径）→ Phase 1 extract 蒸馏移离线（Phase 0 验收后，退化窗口不开）→ Phase 2 认领权派生读（ADR-0260 裁决前置，可与 Phase 3 并行）→ Phase 3 对账收敛（0277 ⑥/⑦ 裁决前置）。

**D6（产品决策，待接受）。** 47 个 extract-only 事实维度的落盘时延从当轮变为下一次 dream pass，是用户可感知的行为变化。建议接受条件：dream 调度周期上界不大于一次会话的自然间隔（会话结束/空闲 N 分钟触发），上界写进调度配置。只能做到每日一次时，需保留一条在线偏好纠正例外通道（那会重新引入第二写者，提案重评估）。

## 3. Alternatives considered（凝练）

- 砍掉 extract：47 个 extract-only 维度直接丢失（其中含无第一人称偏好纠正类隐式事实），不可接受。
- 砍掉工具：remember 晚于 respond，C1 拿不到当轮证据；另有 25 个维度只有工具写过，C10 窄门与 Effect Receipt 一并消失。
- admit 上加第四套 NOOP 闸：`LinkDecider.reconcile` 已有"归一化文本相同即 merged 不新增"分支正是 NOOP 语义，新增平行机制违反 AGENTS.md §4。
- 给 latch 加轮次身份保留双写者：只能关跨轮泄漏，remember 签发的认领权仍当轮无人消费；17/89 重复维度与双实例竞态都在。若 D2 被 ADR 否决，这是次优落点。
- 什么都不做：latch fail-open 缺口当前磁盘上就有未消费的认领权；退役行 34% 占比继续增长；1066 行 consolidation 零引用延续。

## 4. Acceptance criteria（按 Phase，凝练）

- Phase 0：dream 调度落地跑稳，有真实触发证据；周期上界满足 D6 并写进配置；目标 profile 含隐式偏好陈述的 turn 后 `episodes/` 或每日流水有新增。
  - **载体是插件托管的后台循环**，照 `lca/plugins/avatar/plugin.py:302-312` 的 `AvatarCostumeScheduler` 形状（`asyncio.create_task(scheduler.run_forever())` + LIFO dispose），周期上界落在插件 `Config.tick_seconds` 并由 profile YAML 设定。
  - **载体不能是 0268 CronJob。** `CronJob.execution` 是闭合联合 `AgentExecution | SpaceActionExecution`（`lca/contracts/models/cron/models.py:152`，`extra="forbid"` 于 `:144`），`CronWorkerRunner.execute_job`（`lca/infrastructure/cron/worker_runner.py:98-200`）只能投递聊天卡片或 avatar 产物，无法调用 `run_dream` 这样的 Python 函数；加一种 execution kind 是闭集契约变更，按 AGENTS.md §1 第三行须先有 ADR。
  - **周期 CronJob 本身也不会触发。** `next_run` 以精确到微秒的 `datetime` 相等判 `due`（`lca/domain/cron/next_run.py:81-86` interval、`:90-94` hourly、`:101-106` daily、`:112-118` weekly），守护进程在 `asyncio.sleep` 后采样未对齐的 `datetime.now(UTC)`（`lca/infrastructure/cron/daemon.py:44`、`:106`、`:123`）。实测真实 `CronDaemonService` 配真实墙钟、`tick_interval_s=1`，`every_seconds=5` 的任务 30 秒内触发 0 次，同 store 的 `oneshot` 触发 1 次；宿主机 7 个生产 job 全为 `oneshot`。这是全平台缺陷（用户的周期提醒同样永不触发），须单独对 ADR-0268 §232-233 立项修订，不得并入 Phase 0；现有 cron 测试全部注入恰好落在边界的合成时钟，改语义前须先补能区分新旧行为的测试。
  - **载体也不能是 `{home}/routines/`。** 该目录只被计数（`lca/plugins/domain/assistant/catalog/manifest.py:82`），从不解析；`RoutineSpec` 只有必填 `prompt: str`、无可调用字段（`lca/contracts/models/routine/models.py`）；`RoutineTickDriver` 在 `lca/application/routine/` 外零调用方。ADR-0263 已 Accepted（2026-10-05）但状态行自述「Accepted≠Implemented，C1–C5 实施另行排期」。
  - 实施计划：[docs/superpowers/plans/2026-10-04-dream-scheduler-phase0.md](../superpowers/plans/2026-10-04-dream-scheduler-phase0.md)（覆盖 Phase 0 的调度条件）。在线残差捕获条件随 Open question 5 裁决归入本提案 Phase 0，尚无实施计划。
- Phase 1：在线 turn 的 spine 不出现 `phase.reflect.memory.extract` 触发的 `adapter.complete`；残差捕获不随蒸馏一起移走；user/model 双源维度占比 17/89 → 0。
- Phase 2：run 结束后 `claim-latch.json` 不存在；"本轮无写盘 + 含宣称"被拒、"上一轮有写盘 + 本轮无写盘 + 本轮含宣称"被拒；"act 相写盘 + askUserQuestion 暂停 + resume + 含宣称"放行；双 `AssistantMemory` 实例两侧结论一致。
- Phase 3：工具写入同一事实后离线对账产 NOOP，`semantic.json` 行数与退役行数不增长。Remedy：复现 `run_3a523914cc0a` draft，回复原文不被替换。

## 5. Risks

- 47 extract-only 维度的时延是产品决策。退化程度取决于在线捕获能否覆盖该维度，而当前覆盖由 `govern()` 的三个闭合模板决定，与 `governor_enabled` 无关（见 F4）。模板覆盖不到的隐式偏好在 Phase 1 之后是丢失而非延迟，Phase 0 第二个条件就是为此设的。撤回条件：dream 拿不到满足周期上界的调度 → 只落 Phase 2 + remedy（在线双写者 + 轮次作用域认领权）。
- 每日流水的生产写入方已归本提案 Phase 0（Open question 5 裁决，2026-10-05）。承担它把 Phase 0 的范围从调度扩到捕获，`TrailWriter` 的在线调用方与偏好判定拓宽都成为 Phase 0 交付物，Phase 0 的实施计划目前只覆盖调度那一半。
- re-ask remedy 增加一次 LLM 调用，受已有硬上限约束。
- 若 0277 裁决不引入 SemanticClaim，`LinkDecider` 需改造为在 `MemoryRecord` 上工作。
- 若 ADR 否决 D2 的派生读，Phase 2 不启动，latch 保留并补轮次身份（次优落点）。

## 6. Open questions（待拍板，实施不启动）

1. ADR-0260 C1 回执来源重述：修订 0260 或新开 ADR（Phase 2 硬前置）。
2. ADR-0277 ⑥/⑦ 对账闸承载体（Phase 3 硬前置）。
3. ADR-0277 ③ sleep-time 载体与 run_dream 调度归属，及 Phase 0 要求的周期上界。
4. §D6 落盘时延的产品接受（Phase 1 不启动于接受前）。
5. 已裁决（2026-10-05，李超）：每日流水的生产写入方归本提案 Phase 0，不归 ADR-0254 落地。裁决只解决归属，不解决覆盖面。`_PREFERENCE`（`lca/infrastructure/memory/contextfiles/domain/trail.py:18`）为 `偏好|以后|不要|必须|记住|严禁|回复要|请记`，实测对条件二的判据句「还是简洁一点好」「别那么啰嗦」「回复请简短」全部不命中，只有「以后简洁一点」命中；`govern()` 的 verbosity 规则要求 `记住|以后` 合取，同样不命中。因此条件二的交付物是两项，补齐 `TrailWriter` 的在线调用方，以及拓宽 `_PREFERENCE` 与 `govern()` 之一的偏好判定。只做前者，判据仍不达成。

## 7. Related

- ADR：0249（Accepted，双轨）、0260（C1 / §3 / §6.1 / §6.3）、0268（CronJob 调度载体）、0277（Proposed，§2.3 / 待拍板③⑥⑦）、0254（`TrailWriter` 实现来源；落地归属经 Open question 5 改判本提案 Phase 0）
- Note：[语义记忆在线单写者与离线对账归位](../notes/proposed/seam/2026-10-04-semantic-memory-single-online-writer.md)（本 ADR 的证据与论证母体）、[surface/assistant_message 由 think.llm.persist 独家写入](../notes/implemented/seam/2026-10-03-assistant-surface-single-producer.md)（同类"单生产者"先例）、[HIL resume 必须重绑 RunAmbit](../notes/implemented/seam/2026-09-05-hil-resume-rebinds-ambit.md)、[act→think re-ask loop guard](../notes/implemented/2026-09-16-act-think-reask-loop-guard.md)
- Plan：[dream 调度器 Phase 0 实施计划](../superpowers/plans/2026-10-04-dream-scheduler-phase0.md)（载体选型证据与 5 个 TDD 任务）
- 待单独立项：`next_run` 微秒相等导致所有周期 cron 永不触发（对 ADR-0268 §232-233）、`govern()` 贪婪捕获加 40 字符截断污染在产身份事实（F4 末段）
- 证据 run：`run_d30e848f0230`、`run_f4ff17657570`、`run_3a523914cc0a`、`run_5eb9f012455e`、`run_4fcfb6d83c8c`
