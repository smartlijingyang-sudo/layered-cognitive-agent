# Agent Note: 语义记忆在线单写者与离线对账归位

Status: proposed

## Problem

语义记忆有两条在线写入路径，落在 respond 的两侧。

`memory_add` / `memory_update` / `memory_remove`（`lca/infrastructure/tools/assistant/memory_tools.py`）在 act 相执行，产 typed Observation。`phase.reflect.memory.extract`（`bundles/reflect/reflect_subgraph.yaml:30`）在 reflect 相调一次 LLM 蒸馏出 `memory_candidates`，由 `phase.remember.write` 落盘。remember 是五语义闭集的最后一相，它的写入晚于本轮回复定稿。

`run_5eb9f012455e` 的时序钉住了这一点。13:42:23 工具执行，13:42:26 `think.decision.parse` 定稿回复，13:42:43 `phase.remember.write` 落盘。`run_d30e848f0230` 同形。宣称文本产出于工具执行之后的另一次 LLM 轮，模型说话时回执已在它的上下文里。

ADR-0260 C1 要求宣称已记下之前必须有写盘回执。只有工具路径满足这个先后关系。而 `_project_curated`（`assistant_memory.py:233`）对两条路径同等签发认领权，remember 签发的那份当轮无人消费，留在 `{home}/memory/claim-latch.json`，被下一轮的 `take_claim_right`（`assistant_memory.py:108`）读到。下一轮因此在没有任何写盘的情况下可以宣称已记下。

认领权落在磁盘文件上还引入跨实例共享状态。一次 run 构造两个 `AssistantMemory`，一个在 `assistant_memory_tools_from_run`（`memory_tools.py:585`），一个在 runtime。`assistant_memory.py:110-124` 记录了 `run_4fcfb6d83c8c` 中两者不同步导致的错误拒绝，替换文本进入 session log 后被后续每轮读取。

对账有三套实现，在线运行的是临时那套。

| 实现 | 位置 | 运行状态 |
|---|---|---|
| dedupe_key 循环 + 内容指纹循环 | `AssistantMemory._append_semantic`（`assistant_memory.py:466`） | 在线唯一运行 |
| `consolidate` 折叠 episode | `lca/contracts/models/memory/episode.py:102` | 仅 `lca-ops memory dream` 手动 CLI 可达 |
| `LinkDecider.reconcile`，Mem0 四操作 + Zep 非丢失式失效 | `lca/cognition/memory/consolidation.py:239` | 运行时零引用 |

`_append_semantic` 的对账把同维度旧记录标 `deleted` 再追加新行，没有 NOOP 语义。全库 136 行记录中 47 行处于退役态，89 个带 source 的事实维度中 17 个被两条路径各写一次。

ADR-0249（Accepted）§0.1 的问题陈述是「在主对话轮次（`reflect/remember`）中强行调用重量级 LLM，导致单轮高延迟、Token 浪费与幻觉噪音」，规定白天毫秒级残差门控快记与夜晚离线固化双轨。`phase.reflect.memory.extract` 是在线 LLM 蒸馏。ADR-0260 §6.3 已裁决边界，给了用户即时承诺的事实当场写，未承诺的残差信号进做梦管线。

守卫的 remedy 与触发条件的可判定性不匹配。`_CLAIM`（`acknowledgement.py:16`）用正则判定宣称，命中即整条替换回复。`run_3a523914cc0a` 的模型原文是「目前我这边还没有记录你家里人的信息 😅 要不要告诉我？我可以帮你记下来」，其中 `帮你记下` 命中条件式能力提议，本轮无写盘，用户收到 `_REFUSAL`。ADR-0260 §6.1 的方法论是 fail-closed 只用于精确可判定处，文本正则判定宣称不可判定。

## Proposal

语义记忆按 ADR-0249 双轨归位。在线轨单写者，离线轨单一具名对账闸，认领权来自本轮写盘证据。

**在线轨。** `memory_add` / `memory_update` / `memory_remove` 是语义记忆唯一的在线写者。

**离线轨。** `phase.reflect.memory.extract` 的 LLM 语义蒸馏移入 `run_dream`。在线保留毫秒级残差门控（`SalienceGate`、`filter_ingestion_modality`、`EpisodeBuffer`），即 ADR-0249 的 Fast Path。在线捕获已由 `phase.perceive.observe` 每轮无条件触发，其覆盖面受 `govern()` 的闭合模板限制，Phase 0 的第二个条件要求该覆盖面能承接隐式偏好，或补齐等价的捕获路径。`bundles/reflect/reflect_subgraph.yaml` 的三节点拓扑相应收窄，`bundles/base.yaml:172` 的组件声明随之调整。

`run_dream` 的调度是前置条件。它当前的唯一调用方是 `lca/infrastructure/cli/commands/ops/memory.py`，`{home}/routines/` 为空目录，bundles / profiles / deploy 无引用，宿主 crontab 无条目。离线轨在拿到调度之前不承接任何写入。

**认领权。** 来源改为本轮 memory 工具的 Observation。`claim-latch.json` 及其读写路径、`take_claim_right`、`last_curated_receipt` setter 的 latch 副作用退役。ADR-0260 C1 的不变量保持，「一次写盘至多支撑一次用户可见宣称」由轮次作用域保证。此项触及 ADR-0260 §3 明列的非目标，退役前必须先有 ADR 裁决，见 §交付门禁 Phase 2。

轮次边界是 `run_id`。认领权是对本 run journal 中 memory 工具 Observation 的派生读，既不是运行时缓存也不落盘。作用域必须窄到不含另一个 run 的写盘证据，否则上一轮的写盘会支撑本轮的宣称，正是 latch 的泄漏形态；证据助理的会话投影 `tpc_08VEI91yFzbm.jsonl` 一个文件里承载 6 轮对应 6 个不同 `run_id`，`ResumeCursor` 也把 `session_seq`（`terminal_outcome.py:92`）与 run 级 cursor 分成两个轴，所以按会话派生不可用。HIL 暂停与恢复保持同一 `run_id`，`RunSession.ambit` 是跨暂停的 ambient 真值载体，恢复侧不重新解析 providers，见 [HIL resume 必须重绑 RunAmbit](../../implemented/seam/2026-09-05-hil-resume-rebinds-ambit.md)。因此 `askUserQuestion` 暂停后恢复的回复与暂停前的写盘属于同一轮，派生读自然重建认领权，跨暂停不存在悬挂状态。把认领权缓存进实例字段会复现 `run_4fcfb6d83c8c` 那一类双实例不同步，派生读从结构上排除它。

**对账。** 收敛到单一具名闸，具备 ADD / UPDATE / DELETE / NOOP 四操作，重复输入产 NOOP 而不是退役旧行。承载体取决于 ADR-0277 待拍板⑥/⑦。`_append_semantic` 的内联去重与未中选的另一套退役。

**守卫 remedy。** `_CLAIM` 命中且本轮无写盘证据时，经 act→think re-ask 边重写一轮，注入本轮写盘台账，受 [act→think re-ask loop guard](../../implemented/2026-09-16-act-think-reask-loop-guard.md) 的硬上限约束，触顶才落 `_REFUSAL`。`_CLAIM` 收窄以排除条件式能力提议，并补反向回归测试。`think.decision.repair` 不承担此职责，它的范围是 tool-call 参数的确定性 schema 修复。

## 交付门禁

四个 Phase。Phase 0 到 Phase 1 严格串行，前一个的验收未达成则后一个不启动。Phase 2 与 Phase 3 各以自己的 ADR 裁决为前置，在 Phase 1 之后互不依赖，可并行。这是门禁，不是建议顺序。

**Phase 0，离线轨可承接。** 两个条件都满足才算达成，缺一个都不启动 Phase 1。

其一，dream 调度落地并跑稳。载体是插件托管的后台循环，照 `lca/plugins/avatar/plugin.py:302-312` 的 `AvatarCostumeScheduler` 形状，周期上界落在插件 `Config` 并由 profile YAML 设定，且有配置之外的真实触发证据，例如 `{home}/dreams/` 下产物时间戳。`{home}/routines/` 与 ADR-0268 CronJob 都不能作载体，理由见 [Phase 0 实施计划](../../../superpowers/plans/2026-10-04-dream-scheduler-phase0.md) 的载体选型节。调度周期需给出上界并接受 §产品决策待接受 的约束。

其二，目标 profile 的在线残差捕获真的能覆盖隐式偏好。判据是实测而非开关，一个含「还是简洁一点好」这类无记忆动词偏好句的 turn 之后，`{home}/memory/episodes/` 出现 `dedupe_key=preference:verbosity` 且 `explicit_user_authority=true` 的新增文件，或者每日流水补齐生产写入方并由 `is_preference_statement` 命中。这条来自 §产品决策待接受 的实测结论，当前 `govern()` 的模板覆盖不到这类句子。

两条路线目前都覆盖不到判据句，因此本条件有两项交付物。`govern()` 的 verbosity 规则要求 `记住|以后` 合取（`govern.py:59`）。`is_preference_statement` 依赖的 `_PREFERENCE`（`contextfiles/domain/trail.py:18`）为 `偏好|以后|不要|必须|记住|严禁|回复要|请记`，实测「还是简洁一点好」「别那么啰嗦」「回复请简短」「我喜欢简洁的回复」全部不命中，只有「以后简洁一点」命中。第一项交付物是 `TrailWriter` 的在线调用方，归属见 §Open questions 第 5 项的裁决；第二项是拓宽 `_PREFERENCE` 与 `govern()` 之一的偏好判定。只做第一项，判据仍不达成。

Phase 0 未达成时 extract 保持在线，本提案其余部分不启动。

**Phase 1，extract 的 LLM 蒸馏移入离线轨。** 仅在 Phase 0 验收达成后启动。在线保留毫秒级残差门控。47 个 extract-only 维度的落盘时延从本 Phase 起才发生，因此调度必须在本 Phase 之前已经跑稳，退化窗口一天都不开。

**Phase 2，认领权改派生读，latch 退役。** 前置是 ADR-0260 C1 回执来源的裁决已落地。ADR-0260 §3 把「不改 `take_claim_right` 的消费语义」列为非目标，Notes 体系不改老 ADR，因此这一项必须由 ADR 先行裁决，修订 0260 或新开均可，不得随实施 PR 顺手退役。

**Phase 3，对账收敛到单一具名闸。** 前置是 ADR-0277 待拍板⑥/⑦ 的裁决。

## 产品决策待接受

47 个 extract-only 事实维度的落盘时机从当轮变为下一次 dream pass。这是用户可感知的行为变化，需要产品负责人明确接受，不因 ADR-0260 §6.3 已裁决而默认通过。§6.3 裁决的是归属，不是时延。

机制事实决定时延的严重度，其中两条比提案初稿假设的更差。

- 在线残差捕获的门不是开关而是模板。`phase.perceive.observe` 每轮无条件调 `record_task_episode`（`observe.py:62-67`，`913a967ae` 引入），`governor_enabled` 只控制 reflect 侧那一份与 perceive 近冗余的重复写入。真正的门是 `episode_home(runtime)` 能否解析（`daytime.py:17-31`），以及 `govern()` 的三个闭合模板能否命中（`govern.py:21-25`）。verbosity 规则要求 `记住|以后` 合取（`govern.py:59`），因此「别那么啰嗦」「还是简洁一点好」返回 `None`；命中时 `explicit_user_authority` 又被硬编码为 `False`（`govern.py:59-67`），走不到 `_lifecycle` 的首次即提升分支（`contracts/models/memory/episode.py:74-82`）。
- 证据助理跑的就是 `profiles/web-assistant.yaml`，`governor_enabled` 为 true，`memory/episodes/` 仍为空，因为其三轮陈述「i am lee」「上海啊」「我有女儿 儿子 老婆 一家四口」不匹配任何模板。524 个助理 home 中 5 个有 `episodes/`、共 6 个文件，全部是 `residual: instruction` 的身份事实，`preference:verbosity`、`correction`、`error` 各为 0。
- 每日流水 `memory/YYYY-MM-DD.md` 没有生产写入方。`TrailWriter`（`contextfiles/service/trail.py:16`）只被测试构造，24 个助理的 memory 目录下 `20*.md` 计数为 0。`run_dream` 经 `parse_trail` 读它，FTS 索引覆盖它，但没有任何在线路径产生它。
- `AssistantMemory.retrieve` 只读 `semantic.json` 与 `episodic.json`，不读 `memory/episodes/`。捕获到的残差在提升为语义记录之前不进注入路径。
- `memory_search` 的 FTS 索引覆盖 curated records 与 trail files（`contextfiles/service/indexing.py:34`），由 `run_dream` 重建。两次 dream 之间索引是旧的。

结论是捕获覆盖不足，而不是捕获开关未开。`govern()` 命中的残差当轮进 `episodes/`，时延只影响提升，间隔期内这条偏好既不在系统提示里也搜不到，今天随口纠正的偏好在下一次 dream 之前会持续被违反。`govern()` 命不中的隐式偏好，extract 是它唯一的来源，移离线后没有任何捕获路径，这部分维度对应的行为是丢失而不是延迟，直到在线捕获路径补齐为止。唯一能给偏好首次提升的是 trail 路径，`_trail_episode` 在 `is_preference_statement` 命中时设 `authority=True`（`dream.py:137-158`），该正则 `偏好|以后|不要|必须|记住|严禁|回复要|请记`（`contextfiles/domain/trail.py:17`）比 `govern()` 宽得多，而它没有写入方。

时延的可接受度完全由 dream 调度周期决定，而当前周期不存在，`run_dream` 只有手动 CLI 入口。每日一次对偏好纠正不够。`memory_extract.py:64` 放宽成本门正是为了让「还是简洁一点好」这类无第一人称偏好句落盘，把它推迟一天与该意图冲突。

建议的接受条件是 Phase 0 的调度周期上界不大于一次会话的自然间隔，例如会话结束触发或空闲 N 分钟触发，使间隔期落在用户不感知的范围内，并把该上界写进 Phase 0 验收。若只能做到每日一次，离线轨需要保留一条在线的偏好纠正例外通道，那会重新引入第二写者，本提案需要重新评估。

已裁决（2026-10-05，李超）。周期上界为 24 小时。该值正是上面「每日一次」那一档，因此裁决成立的前提是关掉间隔期的读路径缺口，而不是保留在线偏好纠正例外通道。

缺口在读侧而不在写侧。`memory_search` 的 FTS 索引已覆盖 trail files（`contextfiles/service/indexing.py:34`），只是仅由 `run_dream` 重建。让 trail 追加同时增量索引新行，偏好句当轮即可被 ADR-0260 C2 的强制检索命中，且不产生第二个语义写者，`semantic.json` 的在线单写者不变量不受影响。增量索引因此是 Phase 0 条件二的交付物之一，见 [条件二实施计划](../../../superpowers/plans/2026-10-05-trail-capture-phase0-condition2.md)。

这不是免费改动。`MemoryIndex`（`contextfiles/ports/memory_index.py:26`）只声明 `rebuild` / `search` / `close`，`SqliteFtsIndex` 是它唯一的实现，因此增量索引要给该 Protocol 加一个单文档写入方法并同步实现与测试，属 AGENTS.md §5 的公共签名变更。实施计划里单列一个任务。

若增量索引不落地，24 小时上界重新触发本节的重评估条件，因为那时偏好被捕获后最长 24 小时既不进注入路径也搜不到。

## Alternatives considered

### Why not 砍掉 extract，只留工具写？

工具只在模型主动调用时写。extract 覆盖用户没要求记、模型也没调工具的情形，例如无第一人称的偏好纠正。89 个带 source 的事实维度中 47 个只有 extract 写过。砍掉它直接丢这 47 个维度，隐式偏好永不落盘。

### Why not 砍掉工具，只留 extract？

remember 晚于 respond，extract 结构上无法为本轮宣称提供回执。砍掉工具后 ADR-0260 C1 拿不到当轮证据，所有宣称都会被拒。另有 25 个维度只有工具写过，C10 窄门与 Effect Receipt 也随工具一起消失。

### Why not 只在 admit 加一个 NOOP 闸？

那会是第四套对账实现。`LinkDecider.reconcile` 已有归一化文本相同即 `merged`、不新增条目的分支，正是所需的 NOOP 语义。新增平行机制违反 AGENTS.md §4。

### Why not 给 latch 加轮次身份，保留双写者？

轮次身份能关掉跨轮泄漏，但 remember 签发的认领权仍然当轮无人消费，因为它晚于唯一的消费点。双写者还留着 17/89 的重复维度、34% 的退役行占比，以及两个 `AssistantMemory` 实例共享盘上状态的竞态。这是给一个不该存在的状态加字段。

### Why not 只收窄正则？

收窄能修掉 `run_3a523914cc0a` 这一例，但 remedy 仍是整条替换。正则分类器不可判定，误杀会持续发生，每次误杀都把一句与上下文无关的拒绝句写进 session log。跨轮 latch 泄漏与重复写入不受影响。

### Why not 什么都不做？

跨轮 latch 泄漏是 ADR-0260 C1 的 fail-open 缺口，当前磁盘上就留着一份未消费的认领权。退役行按 34% 占比增长，检索侧要持续过滤。ADR-0249 已 Accepted 而实现未接线，`consolidation.py` 及其配套共 1066 行与 6 个测试文件继续处于运行时零引用状态。

## Acceptance criteria

Phase 0。

- `{home}/routines/` 或 ADR-0268 CronJob 中存在 `run_dream` 条目，且有真实触发证据。
- 调度周期上界为 24 小时（2026-10-05 裁决），且该上界写在调度配置里而不是只写在文档里。
- 目标 profile 跑一个含隐式偏好陈述的 turn 后，`{home}/memory/episodes/` 出现新增文件，或每日流水出现当轮追加行。

Phase 1。

- 在线 turn 的 spine 中不出现 `phase.reflect.memory.extract` 触发的 `adapter.complete`。
- Phase 1 之后重跑同一条隐式偏好陈述，`{home}/memory/episodes/` 或每日流水的新增与 Phase 1 之前一致，残差捕获没有随蒸馏一起移走。
- 同 dedupe_key 同时存在 user 与 model 来源的维度占比从 17/89 降至 0。

Phase 2。

- run 结束后 `{home}/memory/claim-latch.json` 不存在。
- 「本轮无写盘 + 回复含宣称」被拒；「上一轮有写盘 + 本轮无写盘 + 本轮含宣称」同样被拒。
- 「act 相写盘 + `askUserQuestion` 暂停 + resume + 回复含宣称」放行；「暂停前无写盘 + resume + 回复含宣称」被拒。两种情形下 `claim-latch.json` 都不存在。
- 一次 run 内构造两个 `AssistantMemory` 实例，工具侧写盘后 runtime 侧解析认领权，两侧结论一致。

Phase 3 与守卫 remedy。

- 同一事实经工具写入后，离线对账产 NOOP，`semantic.json` 的行数与退役行数都不增长。
- 复现 `run_3a523914cc0a` 的 draft，回复原文保持不被替换。

## Risks

- 47 个 extract-only 维度的落盘时延是产品决策，见 §产品决策待接受。Phase 0 门禁保证它在离线轨可承接之前不发生，调度周期上界决定它是否可接受。`govern()` 模板覆盖不到的那部分维度，这个代价是丢失而不是延迟，Phase 0 的第二个条件就是为此设的。
- 每日流水缺生产写入方是独立缺口。`run_dream` 与 FTS 索引都消费它，`TrailWriter` 却只被测试构造。补齐它属于 ADR-0254 的落地范围，不由本提案承担，但 Phase 0 的第二个条件在 governor 关闭的部署上会落到它身上。
- re-ask remedy 增加一次 LLM 调用，上限由已有的 re-ask 硬上限约束，触顶回落 `_REFUSAL`。
- 对账承载体依赖 ADR-0277 待拍板⑥/⑦。若裁决结果是不引入 `SemanticClaim`，`LinkDecider` 需改造为在 `MemoryRecord` 上工作，`consolidation.py` 的类型层随之调整。
- 撤回条件有两条。dream pass 拿不到满足周期上界的调度时离线轨不成立，Phase 1 不启动，退回「在线双写者 + 轮次作用域认领权」，即只落 Phase 2 与守卫 remedy。ADR 裁决否决派生读时 Phase 2 不启动，latch 保留并补轮次身份，跨轮泄漏由轮次作用域关闭，此时 Alternatives considered 里「给 latch 加轮次身份，保留双写者」那一项成为次优落点。

## Open questions

1. ADR-0260 §3 把「不改 `take_claim_right` 的消费语义与拒绝句文案」列为非目标。本提案退役 `take_claim_right`，需要 ADR-0260 C1 的回执来源重述。Notes 体系不改老 ADR，这一项走 ADR 流程，修订 0260 或新开均可。它是 Phase 2 的硬前置，裁决前不启动实施。
2. ADR-0277 待拍板⑥（typed 对象是运行时投影还是新存储真值，与 ADR-0254 v2 决策 A 的关系）与待拍板⑦（`SemanticClaim` 与 ADR-0247 `MemoryRecord` 是替代、包装还是并行）决定对账闸的承载体，是 Phase 3 的硬前置。见 [ADR-0277 四问深审](../../audit-2026-10-03-adr0277-review.md) Q4。
3. ADR-0277 待拍板③（sleep-time 载体）与 `run_dream` 的调度归属是同一件事的两面，需一并裁决，并给出 Phase 0 要求的周期上界。
4. 已裁决（2026-10-05，李超）。接受落盘时延，周期上界 24 小时。接受以 trail 追加的增量索引落地为前提，前提不成立时按 §产品决策待接受 重新评估，Phase 1 在此之前不启动。
5. 已裁决（2026-10-05，李超）。每日流水的生产写入方归本提案 Phase 0，不归 ADR-0254 落地。`TrailWriter` 已实现且受 `DiskFileStore` 的 append-only 窄门保护，缺的是在线调用方，补它成为 Phase 0 条件二的交付物。裁决只解决归属，不解决覆盖面，见 §交付门禁 Phase 0 条件二。

## Related

- ADR：[0249 昼夜双轨记忆固化](../../../adr/0249-cadence-inspired-dual-track-memory-consolidation.md)（Accepted）、[0260 强制检索与写盘铁律](../../../adr/0260-forced-retrieval-and-write-before-claim.md) C1 / §3 / §6.1 / §6.3、[0268 Context Bus、异步执行器与 Cron 投影](../../../adr/0268-context-bus-async-executors-and-cron-projection.md)（Phase 0 调度载体）、[0277 记忆机制的认知重构](../../../adr/0277-cognitive-memory-reconstruction.md) §2.3（Proposed）、[0287 语义记忆在线单写者与离线对账归位](../../../adr/0287-semantic-memory-single-online-writer.md)（本 Note 的契约承载体，Proposed）
- Plan：[Phase 0 条件一，dream 调度器](../../../superpowers/plans/2026-10-04-dream-scheduler-phase0.md)、[Phase 0 条件二，在线流水捕获](../../../superpowers/plans/2026-10-05-trail-capture-phase0-condition2.md)
- Note：[做梦慢路径消费流水、维护亲近度并产出对齐综述](../../implemented/seam/2026-09-30-dream-slow-path.md)、[surface/assistant_message 由 think.llm.persist 独家写入](../../implemented/seam/2026-10-03-assistant-surface-single-producer.md)（同类缺陷先例，一个事实两个生产者）、[HIL resume 必须重绑 RunAmbit](../../implemented/seam/2026-09-05-hil-resume-rebinds-ambit.md)（轮次边界跨暂停的依据）、[act→think re-ask loop guard](../../implemented/2026-09-16-act-think-reask-loop-guard.md)（remedy 的硬上限）
- 证据 run：`run_d30e848f0230`、`run_f4ff17657570`、`run_3a523914cc0a`、`run_5eb9f012455e`、`run_4fcfb6d83c8c`
