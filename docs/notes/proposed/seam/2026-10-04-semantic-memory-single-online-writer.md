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

**离线轨。** `phase.reflect.memory.extract` 的 LLM 语义蒸馏移入 `run_dream`。在线保留毫秒级残差门控（`SalienceGate`、`filter_ingestion_modality`、`EpisodeBuffer`），即 ADR-0249 的 Fast Path。`bundles/reflect/reflect_subgraph.yaml` 的三节点拓扑相应收窄，`bundles/base.yaml:172` 的组件声明随之调整。

`run_dream` 的调度是前置条件。它当前的唯一调用方是 `lca/infrastructure/cli/commands/ops/memory.py`，`{home}/routines/` 为空目录，bundles / profiles / deploy 无引用，宿主 crontab 无条目。离线轨在拿到调度之前不承接任何写入。

**认领权。** 来源改为本轮 memory 工具的 Observation。`claim-latch.json` 及其读写路径、`take_claim_right`、`last_curated_receipt` setter 的 latch 副作用退役。ADR-0260 C1 的不变量保持，「一次写盘至多支撑一次用户可见宣称」由轮次作用域保证。此项触及 ADR-0260 §3 明列的非目标，需 ADR 级确认。

**对账。** 收敛到单一具名闸，具备 ADD / UPDATE / DELETE / NOOP 四操作，重复输入产 NOOP 而不是退役旧行。承载体取决于 ADR-0277 待拍板⑥/⑦。`_append_semantic` 的内联去重与未中选的另一套退役。

**守卫 remedy。** `_CLAIM` 命中且本轮无写盘证据时，经 act→think re-ask 边重写一轮，注入本轮写盘台账，受 [act→think re-ask loop guard](../../implemented/2026-09-16-act-think-reask-loop-guard.md) 的硬上限约束，触顶才落 `_REFUSAL`。`_CLAIM` 收窄以排除条件式能力提议，并补反向回归测试。`think.decision.repair` 不承担此职责，它的范围是 tool-call 参数的确定性 schema 修复。

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

- 在线 turn 的 spine 中不出现 `phase.reflect.memory.extract` 触发的 `adapter.complete`。
- `run_dream` 由调度触发，`{home}/routines/` 或 ADR-0268 CronJob 中存在对应条目。
- run 结束后 `{home}/memory/claim-latch.json` 不存在。
- 「本轮无写盘 + 回复含宣称」被拒；「上一轮有写盘 + 本轮无写盘 + 本轮含宣称」同样被拒。
- 同一事实经工具写入后，离线对账产 NOOP，`semantic.json` 行数与退役行数都不增长。
- 复现 `run_3a523914cc0a` 的 draft，回复原文保持不被替换。
- 同 dedupe_key 同时存在 user 与 model 来源的维度占比从 17/89 降至 0。

## Risks

- 离线轨拿到调度之前，47 个 extract-only 维度对应的行为退化。用户陈述但 agent 未调工具的事实要等 dream pass 才进库，当轮检索不到。ADR-0260 §6.3 接受这个代价，但调度必须先行，否则是丢失而不是延迟。
- re-ask remedy 增加一次 LLM 调用，上限由已有的 re-ask 硬上限约束，触顶回落 `_REFUSAL`。
- 对账承载体依赖 ADR-0277 待拍板⑥/⑦。若裁决结果是不引入 `SemanticClaim`，`LinkDecider` 需改造为在 `MemoryRecord` 上工作，`consolidation.py` 的类型层随之调整。
- 撤回条件：若 dream pass 无法获得稳定调度，离线轨不成立，退回「在线双写者 + 轮次作用域认领权」，即上述 Acceptance criteria 中除调度与 extract 迁移外的条目。

## Open questions

1. ADR-0260 §3 把「不改 `take_claim_right` 的消费语义与拒绝句文案」列为非目标。本提案退役 `take_claim_right`，需要 ADR-0260 C1 的回执来源重述。Notes 体系不改老 ADR，这一项走 ADR 流程。
2. ADR-0277 待拍板⑥（typed 对象是运行时投影还是新存储真值，与 ADR-0254 v2 决策 A 的关系）与待拍板⑦（`SemanticClaim` 与 ADR-0247 `MemoryRecord` 是替代、包装还是并行）决定对账闸的承载体。见 [ADR-0277 四问深审](../../audit-2026-10-03-adr0277-review.md) Q4。
3. ADR-0277 待拍板③（sleep-time 载体）与 `run_dream` 的调度归属是同一件事的两面，需一并裁决。

## Related

- ADR：[0249 昼夜双轨记忆固化](../../../adr/0249-cadence-inspired-dual-track-memory-consolidation.md)（Accepted）、[0260 强制检索与写盘铁律](../../../adr/0260-forced-retrieval-and-write-before-claim.md) C1 / §3 / §6.1 / §6.3、[0277 记忆机制的认知重构](../../../adr/0277-cognitive-memory-reconstruction.md) §2.3（Proposed）
- Note：[做梦慢路径消费流水、维护亲近度并产出对齐综述](../../implemented/seam/2026-09-30-dream-slow-path.md)、[surface/assistant_message 由 think.llm.persist 独家写入](../../implemented/seam/2026-10-03-assistant-surface-single-producer.md)（同类缺陷先例，一个事实两个生产者）
- 证据 run：`run_d30e848f0230`、`run_f4ff17657570`、`run_3a523914cc0a`、`run_5eb9f012455e`、`run_4fcfb6d83c8c`
