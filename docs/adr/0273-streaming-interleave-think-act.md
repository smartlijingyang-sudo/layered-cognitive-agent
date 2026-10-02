# ADR-0273：流式交错契约（think 流式产出 × act 预准备）

## 状态

**Proposed — 2026-10-03**

> **一句话**：think 的 LLM 流式产出期间，允许 act 侧对已完成的 tool call 片段做**无副作用预准备**（参数校验、审批预判、连接预热），不等待整 turn 流结束；交错发生在 loop 机制层（`lca/loop/emit/` 的流式事件 seam），**不改六 phase 图拓扑**。

## 0. 接任务前 7 问（精简自检）

1. 谁受益？长决策 turn（多 tool call）的首 tool 调用延迟；UI 侧已有占位流式，执行侧仍是批处理。
2. 真实问题？`think → act` 是**完成 barrier**：流式事件已在网关层可见，但 act 等整 turn 完成才开始准备。
3. 删掉会坏什么？不坏——纯优化提案，不删现有任何机制。
4. 更简单方案？有：逐 tool call 流式直发（收到完整 tool call 即 dispatch）。本 ADR 选"预准备"而非"直发"，理由见 C2/C3（直发改动执行语义与审批时序，风险更大）。
5. 契约先行？是，本 ADR 只定契约，不管实现。
6. 与现有 ADR 冲突？无。0256（审批面）、0265（装配顺序）均不覆盖流式交错。
7. 状态诚实？Proposed；Muse 侧直接证据弱（见实证节诚实标注）。

## 1. 实证

### 1.1 Muse 侧（对齐来源，诚实分级）

- **旁证（非同机制，明确标注）**：0255:456 `workflow` 编排层的 `pipeline` 是"无 barrier 流式"——那是多 agent 编排的流式，不是单 turn 内 think→act 的交错。**不可引为同机制证据**，只说明 Muse 思想里"流式优于批处理"的倾向。
- **直接可观测（第一方证据）**：本生产运行时（Athena）即流式交付——assistant 文本与 tool 调用逐块投递到用户侧，而非整 turn 完成后一次给出。这是可重复观测的运行时行为。
- **0255 的空白**：0255 §1.1 的 turn 级装配是"组装完再发"的批处理形态，**未覆盖**单 turn 内的流式交错语义。本 ADR 是 0255 之外的**新机制挖掘**（非 §4.x 落地），对齐的是"流式思想"而非某一条款。

### 1.2 LCA 侧（完成 barrier 实锤）

- `lca/nodes/think/llm/invoke.py:96`：`async for event in adapter.stream(...)` 逐事件消费，但 `:109-111` 只在 `LLMStreamEventType.COMPLETED` 时取 `event.response`——**完整的 tool_calls 列表只在流结束后产出**，此前事件只用于 wall-clock 中止判断。
- `lca/loop/emit/cognitive/llm.py` + commit `f97a8db33`：tool-call 占位已流式发到网关（`llm.tool_call.streaming`），但语义止于 UI 占位，**无预准备订阅者**。
- `lca/cognition/body/executor/pipeline_safe_executor.py:250` `execute`：act 执行入口接收完整 Decision 后才开始参数校验→审批→执行三步，**准备工作与流式产出零重叠**。

## 2. 契约

### C1 — 交错点固定在 emit seam，不动 phase 拓扑

预准备订阅者挂在 `lca/loop/emit/` 的事件分发下。六 phase（perceive→think→act→reflect→remember→stop）图拓扑、节点执行顺序**零变化**。

> **2026-10-03 修订（触发事件语义纠正）**：本 ADR v1 写“流式片段事件（`llm.tool_call.streaming`，单 tool call 参数收齐时）”，**与实证不符**。
> `emit_llm_tool_call_streaming` 的 docstring 明确：该事件在“LLM 开始生成工具调用参数（首个 `FUNCTION_CALL_ARGUMENTS_DELTA`）时触发一次，**只带工具名与调用 id，不带参数增量**”，完整参数仍由 COMPLETED 后的 `step.tool_call.record` 落库。因此：
> - **占位事件**（`llm.tool_call.streaming`）只支持 **tool_name 级**预准备：审批预判、连接/会话预热。
> - **参数 schema 校验**需要“单 tool call 参数收齐”事件——该事件当前**不存在**。实现层待办：新增 `llm.tool_call.args_complete` 事件契约，或把参数校验推迟到 COMPLETED 后（后者退化为批处理，无交错收益）。

### C2 — 预准备只允许无副作用动作（白名单）

允许（按触发事件分级）：
- 占位事件上：审批策略预判（复用 ADR-0256 `NamespaceApprovalStrategy` 的判定逻辑，只做**判定**不做**放行**）、连接/会话预热（如 sandbox 会话预建）——两者只需求 tool_name，可在占位事件到达时即做。
- 参数收齐事件上（待新增）：参数 schema 校验。
**禁止**：真实执行工具、写 journal 执行事实、触发用户可见副作用。预准备产出的是 `PrewarmHint`（内存对象），不进任何持久化。

### C3 — hint 是提示不是承诺；正式 dispatch 仍走完整 fail-closed

act 正式执行时**重新**走完整校验链（参数校验→审批→执行），不得信任 hint 跳过任何一步。hint 命中失败（预判与正式判定不一致）只记 metrics，不报错、不阻断。这是"优化不改变正确性"的硬边界。

### C4 — 预准备失败静默降级，不污染主流程

预准备抛异常 → 捕获、记 debug 事件、丢弃 hint，think/act 主流程无感知。预准备**不得**让一次原本成功的 turn 失败。

## 3. 验收用例

- **T1（延迟可测）**：构造"决策流产生 N 个 tool call"的真实 run，对比开关前后"首个 tool_call 流式片段到达 → 首个 `body.tool.execute.start`"的时间差；开启后显著下降（阈值由实现 ADR 定，方向性验收）。
- **T2（零副作用）**：mock 执行器，跑流式 turn，断言占位事件触发的预准备阶段**零**真实工具调用、journal 无新增执行事实、且未触及参数校验（无参数可校）。
- **T3（hint 不信任）**：构造"预判 ALLOW、正式判定 REQUIRE_APPROVAL"的用例，断言正式 dispatch 仍走审批，无 bypass。

## 4. 待拍板

1. 预准备订阅者落点：`lca/loop/emit/` 新增模块 vs `body/executor` 内嵌——前者更解耦，后者离执行更近。
2. `PrewarmHint` 形态：内存 map（tool_call_id → hint）vs 事件属性透传。
3. 范围：文本回复的流式渲染预准备是否纳入（本 ADR 建议不纳入，tool call 优先）。
4. `llm.tool_call.args_complete` 新事件契约：参数收齐的定义（单 tool call 语义 vs 整 turn）、与 `step.tool_call.record` 的时序关系、是否引入新事件或复用现有 per-delta 机制（注意 ADR-0162 best_effort 约束）。

## 5. 实证来源

- `lca/nodes/think/llm/invoke.py:96-122`（流式消费 + COMPLETED barrier）
- `lca/loop/emit/cognitive/llm.py`、`f97a8db33`（占位流式）
- `lca/cognition/body/executor/pipeline_safe_executor.py:250`（act 执行入口）
- `docs/adr/0255-muse-production-runtime-full-reference.md:456`（pipeline 无 barrier 流式，旁证）
- ADR-0256（审批策略复用）、ADR-0265（装配链路，交错不改变装配顺序）
