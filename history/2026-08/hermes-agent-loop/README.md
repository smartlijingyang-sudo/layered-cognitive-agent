# Hermes Agent Loop 对照与 LCA 插件化补齐

**日期：** 2026-08-27

**范围：** 对照 Hermes Agent 官方实现，审视 LCA 的 Agent Loop、插件边界与学习闭环；本记录归档本次调研和实现，不替代当前 ADR 或协议。

## 结论摘要

Hermes Agent 的核心优势不是单一的“模型调用后执行工具”的 ReAct 循环，而是围绕该循环建立了**统一运行内核、受控工具调度、可中断会话、上下文压缩、持久记忆、后台学习复盘与可扩展插件运行时**。[1] [2] LCA 的认知—世界双平面、六步闭集、声明式阶段图、Journal、能力授权和 Profile 组合根，已经为这些能力提供了更严格的架构承载面；因此不应复制 Hermes 的大类 `AIAgent`，而应将每项能力映射到既有的 `Protocol → Seam → Provider / Strategy → Registry → Plugin → Profile` 路径。[3]

本次实现补齐了 Hermes 暴露出的一个关键运行风险：**模型连续发起相同参数的成功工具调用，并持续得到完全相同的结果时，传统“只拦截连续失败”的断路器无法阻止预算耗尽。** `ToolLoopBreakerGate` 现在会在当前候选调用与连续历史调用具有相同工具名、相同规范化参数和相同规范化观察结果时，将决策改写为 `RESPOND`；若观察结果发生变化（例如合法轮询的 queued → running → complete），则不会拦截。该 Gate 由既有 `gate.tool-loop-breaker` 插件贡献给 Think Guard，仍处于认知平面，不执行工具、不直接修改世界、不增加第七认知阶段。

## Hermes 核心能力与 LCA 映射

| Hermes 能力 | Hermes 运行语义 | LCA 对应机制 | 本次判断 |
|---|---|---|---|
| 统一 Agent Loop | 同一个 `AIAgent` 服务 CLI、Gateway、ACP、批处理；负责 prompt、provider、tools、压缩、预算与持久化。[2] | `CognitiveRuntime` 仅持有已验证的声明式 binding；Gateway 通过 `agent_loop` / `run_loop_driver_registry` plugin seam 选择运行实现。 | **已有且更可替换**；不要把逻辑回迁到 Gateway。 |
| 模型—工具迭代 | 模型响应含工具调用时，执行后将结果按顺序写回历史，继续下一轮；文本响应则结束。[2] | 声明式图中的 `perceive → think → act → reflect → remember → stop` 回边；Phase Transaction、Effect Gateway 和 StopRule 分责。 | **已有**；应在 Gate / Effect / Stop 的现有原语内增强。 |
| 工具并发与安全 | 工具可并发，交互工具串行；危险命令经审批，错误规范化为工具结果。[2] [4] | Body / SafeExecutor / Effect Gateway、Approval、idempotency 和 Effect Receipt 已将副作用收口。 | **已有骨架**；执行面需按工具幂等性与交互性继续演进。 |
| 中断、跟随与恢复 | 模型调用可中断；新消息或停止指令不会污染未完成历史。[2] | `CognitiveLiveAgent`、`SessionTurnController`、Inbox、取消 checkpoint 与审批恢复均在 Session Spine 外圈处理。 | **已有**；保持会话控制在 loop 外围。 |
| 预算与无穷循环保护 | 回合预算、上下文压力、重复工具调用问题与 provider fallback 共同限制失控运行。[2] | `Budget`、`LoopGuard`、节点/边访问上限、`RepeatToolCallGate` 与 `ToolLoopBreakerGate`。 | **本次增强**：加入成功但无进展的同参调用熔断。 |
| 上下文压缩与提示稳定 | 对超过阈值的会话压缩中间消息，保留工具调用/结果配对；持久记忆先落盘。[2] | Context Lifecycle、Perceive/Manifest、MemoryPolicy、Journal/Evidence 的目标边界已在宪法中定义。 | **规划中**；应作为 Perceive/Memory 策略，不能改写为 loop 第七步。 |
| 记忆与学习闭环 | 有界记忆、会话搜索和后台复盘；技能创建、修订和 curator 生命周期可审批、可回滚。[5] [6] | `lca-skill-auto-acquire`、失败分析、Profile Evolver 和 `lca-learning-review-lifecycle-subscriber` 都只生成候选，禁止直接发布。 | **正确且更安全**；后续应补 durable review worker、评估和外部推广，而非让模型自行上线。 |
| 插件系统 | manifest + 注册上下文，可注册工具、hook、命令；能力授权与依赖可声明。[7] | Native PluginSpec、audited `PluginContext`、capability DAG、Profile/Bundle Patch、Cordis 生命周期。 | **已有且更严格**；新特性不得绕过 manifest 或在 Gateway 硬编码。 |

## 两个系统的 Loop 链路

Hermes 的一次主回合可概括为：输入与会话恢复 → 稳定系统提示与工具 schema → 上下文预检 / 临时预算提示 → 可中断模型调用 → 解析文本或工具调用 → 策略审批与串/并行工具执行 → 结果写回历史 → 持久化与后台复盘。[2] 这一链路适合面向多供应商 API 的实用型运行时，但核心类承担的职责较多。

LCA 应保留已经确立的六步认知闭集：`perceive → think（含 gate）→ act → reflect → remember → stop`。Context、Journal、协作和执行控制是横切承重系统，并不是可随意附加的步骤；持续控制面只决定何时激活 Session，也不属于认知循环。[3] [8] 因而，Hermes 的具体能力在 LCA 中应按下表分配，而不是集中进入某个超级 orchestrator。

| Hermes 链路阶段 | LCA 正确落点 | 不应采用的落点 |
|---|---|---|
| 会话输入、取消、follow-up、审批恢复 | Session Spine：Inbox、`CognitiveLiveAgent`、`SessionTurnController` | `CognitiveRuntime` 内新增 carrier 分支 |
| provider 格式、重试、流式与降级 | L0 LLM Adapter / Resolver Provider；Profile 选择 | Gateway 的 provider `if/else` |
| Prompt / tool schema / memory / 压缩 | PerceiveHub、ContextManifest、PromptRenderer、MemoryPolicy / CompactionPolicy | 在 Reasoner 私自读取环境并拼装上下文 |
| 工具安全、并发、幂等、审批 | Body / Effect Gateway / SafeExecutor；工具 Provider 的 metadata | Gate 直接调用工具，或工具私改 AgentState |
| 重复调用与预算熔断 | Think 内 Gate 策略与 StopRule / 声明式 LoopGuard | 无界 `while` 或单纯依赖模型自我停止 |
| 终态复盘与技能候选 | Runtime Lifecycle Subscriber + 独立受控 worker | 主 loop 同步写入技能库、Profile 或 capability grant |
| 定时、事件触发、后台重试 | Continuous Control Plane + durable WorkQueue + Session command boundary | 在认知阶段中运行 cron / daemon |

## 本次实现：无进展工具调用断路器

本次变更扩展了 `lca/layer1_cognitive/brain/decision_gates/tool_loop_breaker.py`。原有策略按照同一工具连续失败次数熔断；现在保留该行为，并新增“**工具身份与参数相同，且连续观察结果也相同**”的第二条策略。工具调用指纹仅由 `tool_name` 和 JSON 规范化 arguments 构成，不包含 `call_id`；观察指纹仅由 `success`、payload 和 error 构成。因此每次调用即使产生新 call ID，也不能以此伪造进展。

为了避免误拦截，指纹规范化只接受稳定 JSON 原语、mapping、sequence 与 set。遇到未知 Python 对象时，该分支返回不匹配并放行；已有的“连续失败”保护仍独立生效。这个保守策略使第三方工具的非可序列化载荷不会被不透明地转换为字符串或内存地址，再被错误认定为“相同结果”。

当断路器生效时，Gate 仅把当前 `USE_TOOL` 决策重写成 `RESPOND`，同时沿用 `GateDecided` / `PolicyFact(kind="tool_loop_break")` 记录因果和理由。它不改写 State，不执行 Effect，也不改变阶段图。这符合认知闭集、Reducer 唯一写 State、Journal 可追溯及控制/观察分离等约束。[3]

## 通过插件思维继续补齐的路线

第一阶段应继续将供应商差异限制在 L0 Adapter / Resolver。可新增 Profile 选择的 failover adapter，输入为主 adapter 与按明确错误类别配置的 fallback 链；其重试、切换、使用量和原因都应写入 Journal。该 provider 不能把凭证读取散落到插件内，也不能在运行中静默切换到 mock provider。

第二阶段应将 Context Lifecycle 实作成 Perceive/Memory 群内策略：为模型可见内容创建可验证 ContextManifest，按预算选择稳定系统段、会话近期段、检索段与工具结果段；压缩必须保持一个工具调用和其结果的完整因果边界。压缩产生的是受版本管理的 evidence / materialization，不得成为平行事实源。

第三阶段应完成候选式学习的运行化，但不放松推广治理。现有学习 subscriber 已正确地仅接收终态引用；下一步是通过持续控制平面提供 durable review ticket worker，使用只读证据接口生成 `SkillAcquisitionCandidate` 或失败分析，并将所有修改交由独立 evaluator、留出集、人工审批和可回滚发布路径处理。任何学习插件都不得直接安装 skill、应用 Profile、扩大 capability grant 或启动未授权的后台循环。[5] [6] [8]

## 验证记录

本次实现新增了两个异步回归场景：连续三次 `tool_search` 调用使用相同参数且返回相同成功结果时，下一次调用会被改写为 `RESPOND`；连续三次 `job_status` 使用同一参数但返回不同状态时，下一次调用保持原决策。既有连续失败断路器也继续被覆盖。

执行的验证命令如下：

```sh
uv run ruff check --fix lca/layer1_cognitive/brain/decision_gates/tool_loop_breaker.py tests/test_run_workspace.py
uv run ruff format lca/layer1_cognitive/brain/decision_gates/tool_loop_breaker.py tests/test_run_workspace.py
uv run pytest --no-cov tests/test_run_workspace.py tests/test_ralph_loop_scenario.py tests/test_team_message_publish.py tests/test_v3_full_integration.py -q
```

结果为 **45 passed**。实施前与 loop guard、学习复盘、Gateway plugin 和持续控制面相关的基线测试也通过：**27 passed**。

## 参考

[1]: https://github.com/NousResearch/hermes-agent "Hermes Agent GitHub Repository"
[2]: https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop "Hermes Agent — Agent Loop Internals"
[3]: ../../../docs/design/2026-08-19-cognitive-primitive-constitution-v3.md "LCA 认知原语插件宪法 v3"
[4]: https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime "Hermes Agent — Tools Runtime"
[5]: https://hermes-agent.nousresearch.com/docs/user-guide/features/memory "Hermes Agent — Persistent Memory"
[6]: https://hermes-agent.nousresearch.com/docs/user-guide/features/curator "Hermes Agent — Curator"
[7]: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins "Hermes Agent — Build a Plugin"
[8]: ../../../docs/adr/0093-continuous-control-plane.md "ADR-0093：持续执行控制面"
