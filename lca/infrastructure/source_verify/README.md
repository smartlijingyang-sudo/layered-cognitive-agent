# source_verify —— 来源感知校验

"Getting the Source Right, Not Just the Fact."（ProvenanceGuard,
Multiverse Computing）

## 解决什么问题

会调多个工具的 agent 把多个来源编织成一个答案。现有的事实性检查只问
"这条断言在证据池里有没有支持"，不问"这条断言到底是**哪个**工具的输出
支持的"。于是出现 **cross-source conflation（跨来源混同）**：事实是对的，
但挂在了错的来源上。

> 例：agent 说"根据账户记录，这个套餐含 30 天退款窗口"——30 天是真的，
> 但它写在政策文档里，不在账户记录里。

## 机制（三件套）

1. **来源登记**（`SourceRegistry`）：每条模型可见的工具输出在产生时就
   登记，拿到稳定 `source_id`（`tool:<call_id>`），附带原文内容。来源身份
   从产生一路带到裁决，绝不塌缩成匿名上下文。
2. **模型可见标记**（`source_marker`）：工具结果首行 `[source:tool:<call_id>]`，
   模型引用来源时直接写这个 ID。
3. **生成后校验**（`SourceVerifier.verify`）：对答案中点名了来源的断言——
   - 引用的来源不存在 → `UNRESOLVABLE`（指称幻觉，cf. ADR-0255 §4.8）
   - 断言里的数字/日期/标识符逐字不在引用来源里 → `UNSUPPORTED`（严格字面检查）
   - 字面依据在**别的**已登记来源里 → `CONFLATED`（跨来源混同）
   - 全对 → `SUPPORTED`；没点名来源的断言不 penalize（保守策略）

答案级决定由 `VerifyPolicy` 控制：`OFF` 关闭，`WARN`（默认）只告警不拦截，
`ENFORCE` 拦截可疑答案（需上游接复核/兜底链路）。

## 缝合点

- **采集**：`lca/nodes/concept/effect/execute.py::_append_tool_result_surface`
  ——工具结果成为模型可见的唯一路径；每行登记 `SourceRef`，`meta` 带
  `source_id`，内容首行加 marker。
- **校验**：`verify_final_answer(answer, registry, policy)` 是独立可调用的；
  建议接在最终答案合成后（`convergence/delivery_synth.py`），默认 WARN
  只打日志，不改变既有行为。ENFORCE 模式需要先接好复核/兜底。

## Muse 对齐

- ADR-0255 §4.4：记忆是带出生证明的记录；这里工具输出同样带出生证明
  （`SourceRef`: 谁产生的、何时、原文在哪）。
- ADR-0255 §4.7：事件时间 vs 记录时间区分；`captured_at` 记录证据采集时间。
- ADR-0255 §4.8：点名而不存在 = 指称幻觉；`UNRESOLVABLE` 专门抓这个。

## 后续（未做）

- LLM 语义级 NLI（非字面支持度判断）——当前是严格字面检查，语义蕴含
  需要模型，留作协议缝。
- 记忆/检索来源的登记（`SourceKind.MEMORY/RETRIEVAL` 契约已就绪）。
- 系统提示词里教模型引用 `[source:...]` 标记。
- ENFORCE 模式的复核/兜底链路（论文用 RARR 风格修复循环）。
