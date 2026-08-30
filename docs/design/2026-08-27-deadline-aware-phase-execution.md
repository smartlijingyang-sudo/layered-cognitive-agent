# Run Budget 与阶段执行 Deadline 对齐

**日期：**2026-08-27

**状态：**Implemented

**范围：**在既有六阶段声明式 Agent Loop 内，使每个阶段的重试、执行超时和退避都不能越过该 run 的 wall-clock 预算；不新增认知阶段、事件词表或并行控制路径。

## 问题与结论

LCA 已通过 `PhaseExecutionPolicy` 让 Profile/Bundle 为每个语义阶段声明最大尝试次数、单次 timeout、重试类别、退避和耗尽路径。不过，原先的 `PhaseExecutionRunner` 只执行**阶段局部 timeout**。当 run 设置了 `Budget.max_wall_clock_seconds` 时，单次尝试及其退避可能超过剩余全局时限，直到阶段返回或 timeout 才会由后续 STOP 逻辑发现超额。

这会让两条已经存在且正确的治理轴产生不一致：Profile 选择的阶段容错策略可以限制单次尝试，但 trusted runtime 的 run budget 不能硬性约束该策略。因此，连续 Agent 的核心预算语义仍缺少一次完整闭合。

> **决策：**阶段 timeout 使用 `min(声明的单次 timeout, 当前 run 的剩余 wall-clock)`；无局部 timeout 的阶段仍受剩余 run deadline 约束；退避不允许跨过 deadline。达到 deadline 时，按原有 `timeout` 分类、原有重试次数和 `on_exhausted` 语义收敛，不引入新的图边或恢复旁路。

## 架构边界

| 关注点 | 所属边界 | 本次处理方式 |
|---|---|---|
| 单阶段尝试次数、retry 类别、退避、失败收敛 | `PhaseExecutionPolicy` provider | 保持 Profile/Bundle 的可替换配置；不增加新的 provider。 |
| 全局 wall-clock 预算 | `Budget` 与可信事务内核 | 作为不能被阶段插件扩大或绕过的 hard limit。 |
| 剩余时间计算 | `PhaseExecutionRunner` | 只读取本次 run 已冻结的 `Budget`；每次尝试与退避前重新计算。 |
| 失败建模与图路由 | 既有 `PhaseExecutionFailure`、`route_to_stop` | 复用标准 `timeout` 分类与既有 phase-error 路径。 |
| 状态、事实和副作用 | Reducer、Journal、Effect Gateway | 不创建新的写入通道；超时耗尽仍由原事务写标准失败事实并经过图收口。 |

本设计沿用现有 **Protocol → Plugin Policy → Compiled Plan → Trusted Transaction** 结构。可变的阶段策略继续来自独立的 `phase.execution_policy.resilient` 插件；全局预算强制留在内核，避免一个插件通过配置或自定义 executor 绕过用户/平台设定的最长运行时间。

## 行为规则

| 条件 | 预期结果 |
|---|---|
| 未设置 `max_wall_clock_seconds` | 行为与变更前一致，仅使用阶段策略中的 `timeout_seconds`。 |
| 设置全局时限且局部 timeout 更短 | 使用局部 timeout，保留原重试/退避行为。 |
| 设置全局时限且剩余时间更短 | 以剩余时间作为尝试 timeout，禁止越界执行。 |
| 尝试开始前预算已耗尽 | 不调用 executor；生成标准 `timeout` 尝试失败。 |
| 可重试失败后的退避会跨越 deadline | 不睡眠越界；将本次失败收敛为标准 timeout 耗尽。 |
| `asyncio.CancelledError` 或审批暂停 | 继续原样传播；绝不分类、重试或转换为 deadline failure。 |

## 业界依据

OpenAI 将 agent loop、工具循环、会话、guardrail、可恢复审批与追踪视为不同的运行时能力；其中应用拥有的运行时必须明确管理循环与工具分支。[1] LangGraph 的 interrupt 语义以持久化状态和后续恢复为核心，因此任意可中断运行都必须具有清晰、可预期的执行边界。[2] DeepSeek Harness 则将循环与会话能力纳入 profile 驱动的插件组合，同时保持内核负责插件生命周期与依赖。[3]

本次实现吸收这些模式，但不把 budget enforcement 误做成一个可绕过的观察器或第七阶段。它是对用户设定 run 上限的可信执行约束；选择每阶段如何重试仍是 Plugin Policy 的职责。

## 验收标准

实现与测试必须证明：在 deadline 缺失时完全兼容；局部 timeout 会被全局剩余时间收紧；超时前 executor 未被调用；退避不越过总时限；取消和审批异常保持原语义；默认 Profile 在不修改 phase graph 的情况下使用新的硬约束。

## References

[1]: https://developers.openai.com/api/docs/guides/agents "OpenAI Agents SDK"
[2]: https://docs.langchain.com/oss/python/langgraph/interrupts "LangGraph Interrupts"
[3]: https://deepseek.com/harness/en/ "DeepSeek Harness developer preview"
