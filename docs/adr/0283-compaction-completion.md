# ADR-0283：compaction 机制补齐（压缩前沉淀 + 结构化摘要验收）

## 状态

**Proposed — 2026-10-04**

> **一句话**：`think.context.compact` 经 PR-B 拆分后只剩 `think.context.truncate` 一个策略节点——0.7 预算阈值一到直接按字节砍掉最旧 payload，压缩前没有任何"事实先沉淀"的纪律；`CompactStrategy` 字面量里的 `summarize`/`spill` 全仓无实现节点，契约超前于实现。本 ADR 立四件套：① sediment-before-compact（P0，本轮落地）、② 结构化摘要 + 质量验收（本轮落地）、③ 语义回溯 `recall_compacted`（后续）、④ Phase 降级 `PressurePolicy`（后续）。

## 0. 接任务前 7 问

1. 谁受益？长会话的模型（压缩后不丢决策/承诺/未决事项）；审计方（每次压缩留 `sedimented` 证据，可判定"带病摘要"）。
2. 真实问题？是。本轮读代码实证：`_truncate_oldest_to_byte_budget` 纯字节裁剪，零事实提取；`lca/nodes/think/context/` 仅 `truncate.py` 一个文件，`summarize` 无生产者。
3. 删掉会坏什么？不坏——但长会话的事实丢失继续是 silent 的，且 `summarize` 字面量会一直是个空头契约。
4. 更简单方案？只加 sediment、不加结构化摘要。否决：无结构摘要验收不了 100% 保留率，"丢了什么"说不清，`dropped` 诚实清单无处可放。
5. 契约先行？是。本 ADR 先行，①② 本轮实现 + 测试。
6. 与现有 ADR 冲突？无。0260（写盘铁律）：sediment 走的就是 `AssistantMemory.upsert` 记忆写入通路；0195 §1.4（typed-boundary）：`CompactReceipt` 加字段保持 frozen + `extra="forbid"`；0228 D2（节点形态）：新节点沿用手写 dataclass + `@plugin` 载体。
7. 状态诚实？Proposed。sediment 启发式召回率上限、生产 bootstrap 安装点、③④ 形态待拍板/后续，见 §3。

## 1. 实证（main@072e8868e）

- `lca/nodes/think/context/truncate.py`（252 行）：`ThinkContextTruncateExecutor`，`_COMPACTION_THRESHOLD_RATIO=0.7` 软阈值→`truncate_oldest`→`_TARGET_AFTER_RATIO=0.5`；异常→`CompactReceipt.skipped`。无 sediment、无 summarize。
- `lca/contracts/dto/compact_receipt.py`：`CompactReceipt{compacted, bytes_before, bytes_after, strategy, at}`，frozen，`extra="forbid"`；`CompactStrategy` 含 `summarize`/`spill` 但无生产者；`compact_receipt` 端口全仓零消费者（节点为纯证据型设计，payload 应用是 orchestrator 职责——本轮保持）。
- `think.budget.gate`（`threshold_gate.py:118`）：`next_node="think.context.truncate"`。
- 记忆写入通路：`AssistantMemory.upsert(MemoryRecord)`（`infrastructure/memory/assistant_memory.py:568`）；`metadata={"source": ...}` 透传 provenance；`MemoryCategory` 闭集 {identity, preference, fact, episodic, procedural}——sediment 统一记 `FACT`，细分类进 `metadata["sediment_category"]`。
- 约束：`tests/architecture/test_node_def_count.py`——PR-B 节点 executor ≤4 方法；新节点必须遵守。

## 2. 契约

### 本轮落地（① 压缩前沉淀 + ② 结构化摘要）

- **C1（沉淀先行，P0）**：`think.context.summarize` 在 0.7 阈值上执行 `summarize` 前，必须先跑 sediment pass：从**将被丢弃的 head 区间**提取候选事实（decisions/commitments/实体状态/未决事项），经记忆写入通路落盘，`metadata={"source": "compaction", "sediment_category": ...}`。顺序写死在节点里，不是建议。
- **C2（带病不摘要）**：sediment 抛异常，或候选非空但实际写入数为 0，或无可用 writer → **禁止 summarize**，降级 `truncate_oldest`（receipt 的 `strategy` 诚实记 `truncate_oldest`，`sedimented=0`）。"0 条沉淀 + summarize 发射"是审计红灯，测试钉死。
- **C3（receipt 证据）**：`CompactReceipt` 加 `sedimented: int = 0`；`applied()` 的 `bytes_after <= bytes_before` 不变式不变；frozen + `extra="forbid"` 不变。
- **C4（结构化摘要）**：`CompactSummary{decisions[], commitments[], entity_states[], open_questions[], dropped[], prompt_version}` frozen DTO；`dropped` 诚实填写（被丢弃且未被沉淀条目的截断 repr，上限 20 条）；`prompt_version` 记录所用 prompt 版本。
- **C5（prompt 版本化）**：summarize prompt 独立文件 `lca/nodes/think/context/summarize_prompt.md`，头注版本；`summarize.py` 内 `SUMMARIZE_PROMPT_VERSION` 常量；测试断言两者一致，防漂移。v1 为抽取式确定性实现（可验收 100% 保留率）；LLM 摘要器为后续 seam，prompt 文件即其契约。
- **C6（节点纪律）**：`ThinkContextSummarizeExecutor` 方法数 ≤4（PR-B 约束）；异常→`CompactReceipt.skipped`，永不 raise 出图；输出端口与 truncate 一致（仅 `compact_receipt`），纯证据型。
- **C7（路由）**：`think.budget.gate` 的 under-cap 路由改为 `think.context.summarize`；sediment 失败时节点内部降级为 `truncate_oldest`（不新增图边）。

### 后续（③ 语义回溯 + ④ Phase 降级，本 ADR 只定方向）

- **C8（语义回溯，③）**：`recall_compacted(query)` deferred 工具，搜 summaries + 被压缩区间 traces，带 provenance 返回；默认不占 wire。
- **C9（Phase 降级，④）**：`lca/loop/control/` 首个模块 `PressurePolicy`：压力等级 × phase 优先级表；降级动作记 receipt。

### 已知边界（诚实声明）

- B1：sediment writer 经 ContextVar seam 注入（`sediment_writer_scope`）；生产 bootstrap（run 入口安装 `AssistantMemorySedimentWriter`）为后续工作——未安装时节点 fail-closed 降级，行为等价于现状 truncate。
- B2：v1 sediment 提取为确定性启发式（marker 行 + 结构化 dict），召回率有上限；LLM 提取为后续。
- B3：`compact_receipt` 端口仍无消费者——payload 的实际应用是 orchestrator 职责，本轮不动。

## 3. 待拍板（需李超/Athena 裁决）

1. sediment 启发式召回率上限：是否接受"v1 启发式先行、LLM 提取后续"？
2. 生产 bootstrap 安装点：kernel carrier 还是 run-scope ContextVar（`sediment_writer_scope`）？
3. `recall_compacted`（③）的检索后端：复用现有 semantic 检索还是独立索引？
4. `PressurePolicy`（④）的压力分级阈值与 phase 优先级表。

## 4. 验收（给 tests/quality lane）

- **T1（本轮）**：writer 抛异常 → 禁止 summarize：receipt `strategy="summarize"`、`compacted=False`（或降级 `truncate_oldest`），新 payload 无 `[compact-summary` 标记——"带病不摘要"钉死。
- **T2（本轮）**：无 writer 且候选非空 → 降级 `truncate_oldest`：`strategy="truncate_oldest"`、`sedimented=0`、`bytes_after < bytes_before`。
- **T3（本轮）**：fixtures 埋 8 个已知 facts（2 decision / 2 commitment / 1 entity_state / 2 open_question / 3 噪音）→ `CompactSummary` 关键事实 100% 保留、噪音进 `dropped`、writer 收到 `source="compaction"`。
- **T4（本轮）**：`SUMMARIZE_PROMPT_VERSION` == prompt 文件头注版本；`CompactReceipt` 仍 frozen + `extra="forbid"`。
- **T5（后续）**：`recall_compacted` 语义回溯精度；`PressurePolicy` 降级动作 receipt 审计。

## 决策记录

（空。待李超/Athena 裁决后填写。）
