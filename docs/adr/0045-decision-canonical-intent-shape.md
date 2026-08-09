# ADR-0045: Decision 意图形状归一 —— 防腐层 Canonical Model + Journal 规范正文

## 状态

Accepted

## 背景

LLM 以自由 JSON 表达 Decision 时，常把「回复用户」误写成工具调用，例如：

```json
{
  "action_type": "use_tool",
  "tool_name": "respond",
  "arguments": { "response_text": "……真正的回答……" }
}
```

系统正确形态是：

```json
{ "action_type": "respond", "response_text": "……真正的回答……" }
```

此前有两处结构性缺口：

1. **防腐层只做 action_type 别名**，不做**意图形状**（structural variant）归一；
   `use_tool(tool_name=respond)` 仍进入 Body 找「respond 工具」而失败。
2. **Journal 的 `DecisionMade` 不携带规范正文**；前端 answer 只能从
   `StepTextDelta` 原始 token 里再解析 JSON（ADR-0041 的投影归属），
   解析规则与后端不一致时，气泡直接渲染整段 Decision JSON。

这与框架既有原则冲突：

- ADR-0002：越界决策在**解析期**由防腐层改写，Body 只见词表内 action；
- ADR-0037：Journal-as-Truth——语义在写入期确定，视图是投影，不应各自「考古」；
- ADR-0041：`StepTextDelta` 是中性原始增量；终态归属靠 `DecisionMade` 等事件。

### 业界对照

| 范式 | 做法 | 本 ADR 对齐点 |
|---|---|---|
| DDD Anti-Corruption Layer | 外部模型 → 内部 Canonical Model，边界翻译一次 | `normalize_intent_shape` 在 DecisionParser 内 |
| EIP Message Translator / Tolerant Reader | 多形态入站消息收敛为规范消息 | 声明式形状规则，不散落 if/else 补丁 |
| OpenAI / Claude tool-calling | `respond` 是文本通道，不是 tool 名 | 伪工具（action 伪装 tool）就地改写为 action |
| LangSmith / Journal-as-truth | 事件携带已归一语义，UI 只投影 | `DecisionMade.response_text` 为用户可见正文的权威源 |

## 决定

### 一、DecisionParser 管线增加「意图形状」阶段

归一化管线固定为：

```
LLM 原始文本
  → JSON 提取（extract_json_block）
  → Intent Shape 归一（normalize_intent_shape）   ← 本 ADR 新增
  → action_type 别名归一（ActionRegistry.normalize_alias）
  → 构造 Decision（字段落在规范位置）
  → DegradationPolicy（词表外 action 按内容改写）
  → 词表内 Canonical Decision
```

形状规则（数据驱动，集中在 `decision_shape.py`，禁止在 Body / 前端各自发明）：

1. **伪工具 → 行动**：若 `tool_name`（或别名）解析为已注册 action 且不是
   `use_tool` 本身，则 `action_type` 改写为该 action，并从 `arguments` 提升
   对应字段（`response_text` / `rationale` / `confidence` / 委派字段等），
   清空 `tool_calls` 语义；`degraded_from` 记录原 `action_type`（通常
   `use_tool`）。
2. **正文提升**：`response_text`（及 `response` / `text` 别名）若只在
   `arguments` / `args` / `parameters` 袋中，提升到顶层。
3. **空 use_tool**：`use_tool` 且无有效 `tool_name` 时，已有逻辑改为
   `respond`（保持）。

### 二、`DecisionMade` 携带规范 `response_text`（journal_kind=content）

在 think→act 边界 `record(DecisionMade(...))` 时写入**已经过防腐层**的
`decision.response_text`（非终态动作则为空串）。字段语义与
`SynthesisCompleted.output_text` / `*RunFinished.output_text` 同级：内容字段，
截断策略走 `journal_kind=content`，并带 `output_truncated` 兄弟字段。

投影契约（更新 ADR-0041 实践，不推翻其「后端不预判流式是否答案」）：

- **流式预览**：仍可对 `StepTextDelta` 做 best-effort 提取（仅 UX）；
- **提交主线 answer**：`DecisionMade` 为终态 action 时，**优先**
  `DecisionMade.response_text`；仅当该字段为空时才回退 buffer 提取；
- **run 收尾**：`*RunFinished.output_text` / `SynthesisCompleted.output_text`
  仍为最终落盘权威（与 outcome policy 一致）。

前端不得再依赖「猜 LLM JSON 形态」作为主路径。

### 三、实现落点

| 组件 | 职责 |
|---|---|
| `lca/layer1_cognitive/brain/decision_shape.py` | 纯函数意图形状归一（可单测、无 I/O） |
| `SimpleDecisionParser` | 编排管线；调用 shape → alias → Decision → degrade |
| `DecisionMade` + `record_decision_made` | 写入规范 `response_text` |
| `web/.../chat-projector.ts` | 终态提交优先 journal 字段 |
| `extract-decision-text.ts` | 仅流式预览 mirror 形状规则，文档标明从属后端 |

## 放弃的方案

1. **仅前端正则/嵌套补丁** —— 治标；Body 仍可能对 `tool_name=respond` 抛
   未注册工具；journal 仍无规范正文；与 ADR-0037 相反。
2. **拆成两次 LLM 调用（先定 action 再 stream 正文）** —— 语义最干净，
   但双倍成本并改 ADR-0002 相位；另立评估，不在本 ADR 范围。
3. **强制 provider native structured outputs / tool_choice** —— 长期方向，
   依赖具体 LLM 适配能力；本 ADR 先保证**任意自由 JSON 入站**都收敛为
   Canonical Decision，与 schema 约束可叠加。

## 后果

- 正向：用户气泡不再出现裸 Decision JSON；`use_tool(respond)` 等常见漂移
  在解析期被纠正；前后端对「什么是答案」共享 journal 权威字段。
- 代价：`DecisionMade` 词表增字段，需重生 TS 契约；超长回答受 content
  上限截断（与既有 output_text 一致）。
- 不变量：Body 仍只见词表内 action；StepTextDelta 仍不预判终态。
