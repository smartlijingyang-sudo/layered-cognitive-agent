# ADR-0094：StopPolicy 的 State 群局部性

## 状态

**Accepted — 2026-08-28**

## 背景

Stop Rule 曾同时以 `AgentSpec.stop_rule`、`STOP_RULES` 注册表、`AgentGraph.stop_rule`、`ProductionRuntimeDeps.stop_rule` 和 `CognitiveRuntime.stop_rule` 的形式出现。这个表面把一个只在固定 `stop` 阶段被调用的终止判定提升为完整认知图与运行时的同级事实。

该结构使理解一个停止判断必须跨越 Profile 选择、工厂注册表、组合器、图、运行时绑定和终态策略两个实现模块。接口深度不足：抽象表面大于其可替换价值；`DefaultStopRule` 与 `DefaultStopOutcomePolicy` 的拆分也没有形成两个独立的真实 seam。删除测试表明，删除后者只会把完成、预算耗尽和输出收口逻辑集中回终止策略，因此该适配器不应存在。

## 决策

`StopPolicy` 是 **State 群 Provider**，并且只作为 `stop_policy` 注入 `Stop` 阶段的 `phase_capabilities`。它不是 `AgentSpec` 选择轴、工厂注册表项、`AgentGraph` 字段、生产运行依赖字段或 `CognitiveRuntime` 的公共属性。

默认实现 `DefaultStopPolicy` 位于 `lca.plugins.state.stop_policy`。该深 module 在同一局部性中处理：响应完成、handoff、预算耗尽、终态状态和 artifact closure；其唯一接口是 `StopPolicy.decide(state, decision, observation, reflection) -> StopDecision`。

| 位置 | 所有者 | 允许的职责 | 禁止的职责 |
|---|---|---|---|
| `lca.plugins.state.stop_policy` | State 群 Provider | 提供一个可替换 `StopPolicy`；集中终止判定与输出收口 | 读取环境中的 Profile 选择；写入状态；执行副作用 |
| `PerceiveComposer` | State 群组合 seam | 解析 `stop_policy` 并向 `phase_capabilities` 贡献 | 将策略写入完整 AgentGraph；按 AgentSpec 名称选择策略 |
| `StandardStopExecutor` | 固定 Stop 阶段 | 通过局部能力调用 `StopPolicy.decide` 并投影 `StopDecision` | 内联终止业务规则；向运行时泄露策略 |
| `CognitiveRuntime` / `ProductionRuntimeDeps` | 最小可信运行内核 | 携带冻结的阶段能力映射 | 持有或公开 StopPolicy / StopRule 顶层字段 |
| Profile / Bundle | 组合根 | 选择一个 State 群 StopPolicy Provider | 生成 per-agent 停止策略选择轴 |

## 后果

停止策略有一个真实的替换 seam：Profile 能替换 State 群 Provider，而固定 Stop 阶段的接口和认知闭环不变。实现由双层浅 module 收敛为一个更深的 module，缩小了完整图、运行时和 AgentSpec 的接口面，并将未来终止规则的变更局限在 State 群与 Stop 阶段测试。

`StopDecision` 与 `StopReason` 仍是跨阶段的纯数据契约；`TerminalOutcome` 仍由 Reducer 从 StopDecision 派生。此决策不改变六阶段循环、Reducer 单写纪律、Journal-as-Truth 或 `control.stop.decide` 的控制槽。

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 保留 `AgentSpec.stop_rule` 与 `STOP_RULES` | 为每个 Agent 增加一个没有实际需求的顶层选择轴，扩大组合接口且削弱局部性。 |
| 保留 `StopRule` 和 `StopOutcomePolicy` 两层 | 二者没有独立替换或消费路径；删除测试显示第二层只会移动复杂度。 |
| 让 `CognitiveRuntime` 持有 `stop_policy` | 使固定阶段的局部依赖重新成为运行时事实，并诱导控制逻辑绕过 Stop executor。 |
| 将判定写入 `StandardStopExecutor` | 失去 Profile 级替换 seam，并使阶段执行器承担业务策略。 |

## 验证约束

- `AgentSpec`、`AgentGraph`、`ProductionRuntimeDeps` 和 `CognitiveRuntime` 不得声明或公开 `stop_rule` / `stop_policy` 顶层字段。
- `StandardStopExecutor` 必须仅从局部 `stop_policy` 能力调用 `StopPolicy.decide(...)`。
- 默认 Profile 必须显式启用 `state.stop-policy.default`，其 `provides` 为 `stop_policy`，并要求 `artifact_closure`。
- `DefaultStopPolicy` 必须覆盖 respond、handoff、预算耗尽和继续循环语义；预算耗尽时必须使用注入的 artifact closure。
- StopPolicy 的替换不得改变 `control.stop.decide`、Reducer 终态投影或六阶段执行顺序。
- 不得恢复 `StopRule`、`StopOutcome`、`StopOutcomePolicy`、`STOP_RULES` 或旧的 runtime Stop Rule Provider。

## 关联

本决策细化 ADR-0074 的 `stop.decide` 原子控制槽、ADR-0075 的最小可信运行内核、ADR-0076 的能力布局及 ADR-0088 的 Profile 选择完整运行时原则；不重开这些 ADR 的既有结论。

本文档取代项目中关于 `DefaultStopRule`、`StopOutcomePolicy` 和 `STOP_RULES` 的现役实现指引。
