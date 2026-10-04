# ADR-0287: 语义记忆在线单写者与离线对账归位

> **Status: Proposed**（2026-10-04 起草）
> 本提案把李超的 note《语义记忆在线单写者与离线对账归位》（`docs/notes/proposed/seam/2026-10-04-semantic-memory-single-online-writer.md`）转成 ADR 契约提案。Note 本身已把两项跨 ADR 的依赖标注为"升级待裁决"，本 ADR 是提案承载体，**未落地任何代码，不改变任何现状**。

## 1. Context（发现）

语义记忆有两条在线写入路径，落在 respond 的两侧：`memory_add` / `memory_update` / `memory_remove`（act 相，产 typed Observation）与 `phase.reflect.memory.extract`（reflect 相 LLM 蒸馏）→ `phase.remember.write`（remember 相落盘，晚于本轮回复定稿）。`run_5eb9f012455e` 钉住时序：工具执行 13:42:23，`think.decision.parse` 定稿 13:42:26，`phase.remember.write` 落盘 13:42:43。

**F1（认领权跨轮泄漏，ADR-0260 C1 的 fail-open 缺口）。** ADR-0260 C1 要求"宣称已记下之前必须有写盘回执"；只有工具路径满足这个先后关系。但 `_project_curated` 对两条路径同等签发认领权（`assistant_memory.py:233`），remember 签发的那份当轮无人消费，落在 `{home}/memory/claim-latch.json`，被下一轮 `take_claim_right`（`assistant_memory.py:108`）读到——下一轮因此在没有任何写盘的情况下可以宣认已记下。`_LATCH_FILE = "claim-latch.json"`（`lca/infrastructure/memory/assistant_memory.py:67`）。认领权落盘还引入跨实例共享状态：`run_4fcfb6d83c8c` 中两个 `AssistantMemory` 实例对 latch 不同步导致错误拒绝。

**F2（对账三套实现，在线运行的是临时那套）。** `_append_semantic` 内联去重（在线唯一运行）/ `consolidate`（episode 折叠，仅 `lca-ops memory dream` 手动 CLI 可达）/ `LinkDecider.reconcile`（`consolidation.py:239`，运行时零引用）。内联去重无 NOOP 语义：136 行中 47 行退役态，89 个带 source 的事实维度中 17 个被两条路径各写一次。

**F3（ADR-0249 双轨 Accepted 但实现未接线）。** 0249 §0.1 要"毫秒级残差门控快记 + 夜晚离线固化双轨"；`phase.reflect.memory.extract` 仍是在线 LLM 蒸馏，`consolidation.py` 及其配套共 1066 行处于运行时零引用。

**F4（每日流水与 episode 缓冲的捕获缺口）。** `TrailWriter` 只被测试构造（`tests/infrastructure/memory/test_trail_append_only.py`、`tests/scenario/memory/test_adr0254_feature_matrix.py`），24 个助理 home 的 `memory/20*.md` 计数为 0，但 `run_dream` 经 `parse_trail` 读它、FTS 索引覆盖它——两个消费者对着一个无生产者写者的文件。`EpisodeBuffer` 只在 `governor_enabled` 为真时写，插件默认 `False`（24 助理中 5 个有 `memory/episodes/`）。

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

- Phase 0：`{home}/routines/` 或 0268 CronJob 有 `run_dream` 条目 + 真实触发证据；周期上界满足 D6 并写进配置；目标 profile 含隐式偏好陈述的 turn 后 `episodes/` 或每日流水有新增。
- Phase 1：在线 turn 的 spine 不出现 `phase.reflect.memory.extract` 触发的 `adapter.complete`；残差捕获不随蒸馏一起移走；user/model 双源维度占比 17/89 → 0。
- Phase 2：run 结束后 `claim-latch.json` 不存在；"本轮无写盘 + 含宣称"被拒、"上一轮有写盘 + 本轮无写盘 + 本轮含宣称"被拒；"act 相写盘 + askUserQuestion 暂停 + resume + 含宣称"放行；双 `AssistantMemory` 实例两侧结论一致。
- Phase 3：工具写入同一事实后离线对账产 NOOP，`semantic.json` 行数与退役行数不增长。Remedy：复现 `run_3a523914cc0a` draft，回复原文不被替换。

## 5. Risks

- 47 extract-only 维度的时延是产品决策；没开 governor 的 profile 上是丢失而非延迟，Phase 0 第二个条件就是为此设的。撤回条件：dream 拿不到满足周期上界的调度 → 只落 Phase 2 + remedy（在线双写者 + 轮次作用域认领权）。
- 每日流水缺生产写入方是独立缺口（归 ADR-0254 落地，本提案不承担），但 Phase 0 在 governor 关闭的部署上会落到它身上——Open question 5 谁补。
- re-ask remedy 增加一次 LLM 调用，受已有硬上限约束。
- 若 0277 裁决不引入 SemanticClaim，`LinkDecider` 需改造为在 `MemoryRecord` 上工作。
- 若 ADR 否决 D2 的派生读，Phase 2 不启动，latch 保留并补轮次身份（次优落点）。

## 6. Open questions（待拍板，实施不启动）

1. ADR-0260 C1 回执来源重述：修订 0260 或新开 ADR（Phase 2 硬前置）。
2. ADR-0277 ⑥/⑦ 对账闸承载体（Phase 3 硬前置）。
3. ADR-0277 ③ sleep-time 载体与 run_dream 调度归属，及 Phase 0 要求的周期上界。
4. §D6 落盘时延的产品接受（Phase 1 不启动于接受前）。
5. 每日流水生产写入方由谁补（ADR-0254 落地 vs 本提案 Phase 0）。

## 7. Related

- ADR：0249（Accepted，双轨）、0260（C1 / §3 / §6.1 / §6.3）、0268（CronJob 调度载体）、0277（Proposed，§2.3 / 待拍板③⑥⑦）、0254（TrailWriter 落地归属）
- Note：[语义记忆在线单写者与离线对账归位](../notes/proposed/seam/2026-10-04-semantic-memory-single-online-writer.md)（本 ADR 的证据与论证母体）、[surface/assistant_message 由 think.llm.persist 独家写入](../notes/implemented/seam/2026-10-03-assistant-surface-single-producer.md)（同类"单生产者"先例）、[HIL resume 必须重绑 RunAmbit](../notes/implemented/seam/2026-09-05-hil-resume-rebinds-ambit.md)、[act→think re-ask loop guard](../notes/implemented/2026-09-16-act-think-reask-loop-guard.md)
- 证据 run：`run_d30e848f0230`、`run_f4ff17657570`、`run_3a523914cc0a`、`run_5eb9f012455e`、`run_4fcfb6d83c8c`
