# ADR-0041: PromptReasoner 接入流式增量文本；answer-delta 归属交给前端投影

## 状态

Accepted

## 背景

以下几点为 2026-08 代码库核实事实：

- `docs/adr/0038` 定义了 provider-neutral 的 `LLMStreamEventType` /
  `LLMStreamEvent` 契约，并让 `TelemetryLLMAdapter.stream()` 透传事件、在
  `COMPLETED` 时记录真实 token，但明确排除「把 stream() 接进
  reasoner.py / 认知回路（零生产调用方，另立 ADR）」。本 ADR 就是那篇
  续篇。

- `lca/cognition/brain/reasoner.py::_complete_candidates` 当前对每个
  候选调用 `await llm.complete(prompt, tools=tools)`；`PromptReasoner
  .generate_thoughts(state, n=1)` 是 think() 阶段（`CognitiveRuntime
  .think`）唯一调用点，且生产代码从未以 n>1 调用——think() 直接
  `self.reasoner.generate_thoughts(state)`，不传 n。ADR-0035 已废除
  「候选竞争」语义（`generate_candidates` → `generate_thoughts` 改名即为
  此事的化石注记），n>1 目前只在测试里被直接调用，不是生产路径。

- journal 事件的登记机制（`journal_catalog.py`）是「一个 dataclass +
  `JOURNAL_CATALOG` 一行登记 + AST 守卫强制的单一发射模块前缀」；现有
  `LlmCallCompleted` 的登记发射模块是 `lca.infrastructure.observability
  .adapters`（即 TelemetryLLMAdapter 所在包），reasoner.py 本身没有、
  也不应该有任何 `record()` 调用——遥测与业务行为分离是既有约定。

- journal 词表里已经存在若干「终态内容」事件，字段带
  `metadata={"journal_kind": "content"}`：`AgentRunFinished.output_text`、
  `TeamRunFinished.output_text`、`SynthesisCompleted.output_text`。这些都
  是运行/综合结束时一次性给出的完整文本，不是增量；且它们分别对应
  solo/最终 run、board 等 mandate 下 lead 的收口综合——也就是说，代码库里
  「这段文本是不是最终答案」这件事，此前只在生成结束之后才有信号，
  生成过程中从未有过增量信号。

- `CognitiveRuntime.think()` 的调用顺序是先
  `raw_candidates = await self.reasoner.generate_thoughts(state)`，再
  `decision_parser.parse(rc, state)` 解析出 `Decision.action_type`——也就
  是说，某一次 LLM 生成在开始产出文本时，代码路径本身还不知道这次生成
  最终会被解析成 respond/finish 还是 delegate/tool_call。

- 前端 `chat-projector.ts` 目前用 `splitSentences` 对已经完整拿到的文本做
  「假流式」逐句显现，代码注释自陈这是「真 token 流接入前顶一顶」；提案
  `docs/proposals/0001-frontend-productization.md` §3.6 已经为此预留了
  数据源切换点（重命名为 `useProgressiveReveal`，`AssistantBubble` 组件
  契约不因切换 transport 而改变）。

## 决定

### 一、reasoner.py 内部改用 stream() 拼接，n=1 是覆盖范围

`_complete_candidates` 在 n == 1（当前唯一生产路径）时改用
`llm.stream(prompt, tools=tools, step=state.step)`，累积
`LLMStreamEventType.OUTPUT_TEXT_DELTA` 的文本得到与今日 `complete()` 等价
的最终字符串，交给既有 `decision_parser.parse`——决策解析仍然只读取拼接后
的完整文本，不做增量解析（增量解析工具调用参数/JSON 结构的正确性在传输
中途无法保证，超出本 ADR 范围，见「放弃的方案」）。n > 1 路径（当前无
生产调用方）保持逐个 `complete()` 循环不变，不因本 ADR 变更。

reasoner.py 本身不新增任何 telemetry/journal 代码，延续「遥测与行为
分离」——它只是把内部 LLM 调用方式从 `complete()` 换成 `stream()` 再拼接；
谁负责把增量文本发成事件，见二。

### 二、新增 journal 事件 StepTextDelta，发射点复用 LlmCallCompleted 同一模块前缀

`TelemetryLLMAdapter.stream()` 在把每个 `OUTPUT_TEXT_DELTA` 事件透传给
调用方之前，`record()` 一条 `StepTextDelta`：`trace_id`/`run_id` 由既有
RunScope 盖章机制提供；`step` 由调用方经 `stream(..., step=state.step)`
传入的 kwargs 提取；`text_delta`（`journal_kind: "content"`）即该分片文本；
`seq` 为同一 step 内的单调序号，供消费方兜底排序。发射模块仍是
`lca.infrastructure.observability.adapters`，与 `LlmCallCompleted` 同前缀，
不新增发射点归属，`JOURNAL_CATALOG` 按同样方式登记一行、`VocabDomain`
取 RESOURCE（与 `LlmCallCompleted` 同域，二者都描述同一次 LLM 调用的
不同侧面）。

### 三、后端不在发射时判定「这是不是最终答案」

think() 生成文本时 `decision_parser.parse` 还没跑，无法预知这次生成
最终会被解析成面向用户的终态动作还是内部委派/工具调用动作；提前判断需要
重排「先决策类型、再生成正文」的认知回路顺序，超出本次改动范围（且与
ADR-0002 固定的 perceive→think→act→observe→reflect→update 顺序冲突，见
「放弃的方案 2」）。因此 `StepTextDelta` 在发射时是中性的「某步骤的原始
增量文本」，不预判、也不需要预判是否为终态答案。

### 四、终态归属交给前端投影层判定

复用既有「journal 是唯一真相，多个投影各自归约」的模式（ADR-0037；
`chat-projector.ts` / `trace-projector.ts` 并存不冲突）：`chat-projector
.ts` 按 `(run_id, step)` 缓冲 `StepTextDelta` 分片；当同一 `(run_id, step)`
之后收到 `DecisionMade`（`action_type` 为面向用户的终态动作）或该 run 的
`AgentRunFinished` / `TeamRunFinished` / `SynthesisCompleted`（其
`output_text` 与缓冲拼接结果理应一致，可互为校验）时，才把已缓冲的分片
提交为 `AssistantBubble` 的可见增量文本；其余步骤的分片只进入
`trace-projector.ts`（开发者模式可见）——呼应产品定位「团队协作过程即
卖点」，而非把中间思考藏成不可见的思维链。这正是提案 §3.6 为「假流式」
预留的数据源切换点：`useProgressiveReveal` 换成消费真实 `StepTextDelta`
序列，`AssistantBubble` 组件契约不变。

`answer-delta` 这个名字保留给前端投影层的输出（`chat-projector.ts`
对外暴露的、已确认属于可见回答的增量文本流），不作为后端 journal 事件类
名——这是与最初提法唯一的偏离，理由见「放弃的方案 1」。

## 放弃的方案

1. **journal 事件直接命名/语义为 AnswerDelta，发射时即认定为终态答案**
   — 技术上做不到：生成阶段结束前 decision_parser 未解析，无法确定该
   步骤是否终态；勉强命名会让「事件名」和「事件实际语义」长期不一致
   （board/routing 等团队模式下多数步骤是委派/工具调用，被命名为 answer
   会误导消费者）。

2. **拆分「决策生成」与「最终作答生成」为两次独立 LLM 调用**（先低成本
   `complete()` 决定 action_type，若为终态动作再单独 stream() 生成
   正文）—— 能让「是否为答案」在生成前就已知，天然贴合字面 answer-delta
   语义，但双倍 LLM 调用（延迟 + 成本），且改变 ADR-0002 固定的认知闭环
   相位划分，影响面远大于本 ADR 的既定范围，值得单独评估但不在此次决定。

3. **StepTextDelta 只走 SSE 广播、不写入 jsonl**（避免 token 级别事件
   膨胀 replay 文件）—— 当前 ObservabilityHub / journal_projectors
   没有按事件类型选择性路由的机制，引入需要新建投影分发层，属于新机制而
   非复用；典型回答的 delta 总量（数百到两千 token 量级）相对现有 verbose
   档位的 journal 用量并不夸张，先落地统一路径，如果实测 jsonl 体积/回放
   性能确有问题，再单独评估选择性路由。

4. **与「多轮上下文组装」（proposal §6 第 3 行，"涉及认知回路，建议单独
   ADR"）合并成一篇** —— 两者都涉及认知回路，但相互独立（一个是「生成时
   怎么把文本吐出来」，一个是「生成前怎么组装历史上下文」），合并会让
   评审面过宽，拆开更利于各自过审。

## 后果

### 正面

- 首次有真实逐 token 流式抵达前端，`splitSentences` 假流式可以按 §3.6
  已经预留的接口位置退休为过渡态实现，`AssistantBubble` 组件契约不变。
- `StepTextDelta` 复用 `TelemetryLLMAdapter` 现有发射点与 RunScope 盖章
  机制，不新增架构层，不违反「一事件一发射点」守卫。
- 团队协作过程中「思考中」的文本（委派前的决策文本、工具调用前的思考
  文本）第一次有了增量可见性，落在 trace-projector 一侧，进一步兑现
  「团队协作过程是产品卖点」的定位，而不只是终态答案。

### 负面

- `PromptReasoner` 内部实现从「一次 await 拿到完整文本」变为「消费异步
  迭代器再拼接」，是行为改动而非纯新增，需要覆盖现有 reasoner 测试，
  新增断言确保拼接结果与原 `complete()` 路径逐字符相等（ADR-0038 已有的
  「COMPLETED.response 与 complete() 返回值逐字段相等」不变式，在这里
  延伸为「拼接后的 delta 文本与 complete() 的 text 逐字符相等」）。
- 「终态归属」判定被下放到前端 `chat-projector.ts`，后端 journal 本身不
  再保证「看到这条事件就知道它是不是答案」，消费方（未来任何新前端/第三方
  集成）必须自己实现「缓冲 + 按 DecisionMade 提交」的归约逻辑，不能只看
  事件类型判断。这是本 ADR 刻意的取舍（见「放弃的方案 1」），但确实增加了
  消费方心智负担，需要在前端契约文档里把这条归约规则写清楚，否则容易被
  下一个实现者遗忘。

### 明确排除

- 不重排认知闭环相位或拆分决策/作答为两次 LLM 调用（「放弃的方案 2」）。
- 不解决多轮上下文组装（proposal §6 第 3 行），另立 ADR。
- 不引入按事件类型选择性投影路由的新机制（「放弃的方案 3」），jsonl 与
  SSE 继续同源同步。
- 不改变 LLMAdapter / LLMStreamEventType / LLMStreamEvent 契约本身
  （ADR-0038 已定稿），本 ADR 只是让消费方（reasoner.py +
  TelemetryLLMAdapter）首次真正使用它。

## 相关

- **Extends:** ADR-0038（LLMAdapter 流式事件契约）—— 本 ADR 正是其「明确
  排除」里预告的续篇。
- **Keeps:** ADR-0037（Journal-as-Truth，journal_projectors 多投影模式
  不变）、ADR-0002（认知闭环相位顺序不变）、ADR-0035（候选竞争语义已废除，
  n=1 是唯一生产路径这一前提不变）。
- **呼应:** `docs/proposals/0001-frontend-productization.md` §3.6 第 1 点为
  「假流式」预留的接口位置、§6 第 4 行「真实逐 token 流式」待办。
- **落地:** `docs/proposals/0002-lobehub-parity-polish.md` §2.1/§2.3 前端
  投影层在语义边界持久化与流式 Markdown 渲染，与本 ADR 的 answer-delta 归属
  判定一致。
