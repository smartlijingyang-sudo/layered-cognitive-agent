# Agent Loop 生命周期事件发布：插件化设计与实施

**日期：**2026-08-27

**状态：**Implemented

**作者：**Manus AI

## 审查结论

LCA 的主循环已经具备生产 Agent 的关键执行正确性：声明式 phase graph、受限 capability 闭合、Journal、Effect Gateway、Reducer 单写、预算与 loop guard、checkpoint/resume、审批暂停及终态投影均已落在明确边界中。`CognitiveAgent` 则继续作为不可省略的外层审计边界，记录 Agent 的开始、恢复与完成事实。

审查发现的主流能力缺口不在于再增加一个认知阶段，亦不在于把 Journal 或 reducer 交给扩展插件，而是**为长时、可暂停 Agent Loop 提供独立、可组合且安全的运行期生命周期投影接口**。此前，phase observer 只能包裹单个 phase，且经过刻意设计不能影响控制流；外部进度面若需获知开始、恢复、等待输入、完成、失败或取消，只能耦合具体 carrier，或者读取 Journal 的实现细节。

| 已有机制 | 已解决的问题 | 本次保持不变的边界 |
|---|---|---|
| `DeclarativeRuntimeBindings` | 在运行前冻结 plan、executor、effect、reducer、checkpoint 与终态依赖 | 不新增运行期 ambient lookup |
| `GenericPlanInterpreter` | 解释 phase graph、重试/恢复边和 loop guard | 不向插件公开 phase transaction |
| `RuntimeResultFinalizer` | 通过 Hook、Reducer 和投影生成统一终态结果 | 不绕过 Journal、Reducer 或 checkpoint |
| `PhaseObserver` | 每 phase 的只读 trace / 诊断观察 | 不赋予 observer 控制或状态写入能力 |
| `CognitiveAgent` 生命周期事实 | 外层 Agent 的 durable start / resume / finish 审计 | 不以插件替换或省略内核审计事实 |

## 业界对照

LangGraph 的动态 interrupt 在中断点持久化图状态，并通过稳定的线程标识恢复；其恢复模型会重新进入节点，因此要求中断前的副作用可幂等。事件流可将中断、状态快照及完成输出投影给外部消费者。[1] LCA 已有 checkpoint、cursor、Effect Gateway 幂等性与审批恢复语义，因此适合补足与这些运行边界一致的进度投影，而非重复实现暂停机制。

OpenAI Agents SDK 将模型执行循环、工具调用、guardrail、handoff、会话/记忆、流式事件、追踪与错误恢复设为分离能力，并允许应用在需要时拥有更高层的循环编排。[2] 对 LCA 而言，这支持将**生命周期发布**作为独立横切能力，而不把 UI/SSE、遥测或审计需求硬编码进 phase executor、runtime factory 或 Gateway carrier。

> 设计原则：扩展点可以看到**不可变投影**，但不得接触可写执行状态与控制依赖；核心 Loop 继续唯一拥有 phase 事务、Journal、Effect Gateway、Reducer、checkpoint 及终态协议。

## 实施方案

本次实现采用与 phase observer 一致的 **Registry → Contribution → Composite Provider → Frozen Runtime Binding** 模式。该模式使每一个进度桥、审计消费者或遥测导出器可以作为独立插件贡献订阅者，而 Profile 决定其是否启用、排序与故障策略。

| 层次 | 新增组件 | 责任 |
|---|---|---|
| Contract | `RuntimeLifecycleEvent`、`RuntimeLifecyclePublisher`、`RuntimeLifecycleSubscriber` | 定义只读、最小化的事件与异步发布协议 |
| Seam | `runtime_lifecycle_subscriber_registry` | 在 Profile boot 期收集唯一、带优先级的订阅贡献 |
| Provider | `lca-runtime-lifecycle-logging-provider` | 默认贡献结构化日志投影；不产生控制 effect |
| Composite | `lca-runtime-lifecycle-publisher` | 冻结排序后的贡献，并执行 `fail_open` / `fail_closed` 策略 |
| Runtime binding | `DeclarativeRuntimeBindings.lifecycle_publisher` | 将 Profile 已解析的发布器固定到每个 Loop 的依赖闭合 |
| Runtime boundary | `CognitiveRuntime.run()` / `.resume()` | 生成 `started`、`resumed`、`completed`、`partial`、`input_required`、`failed`、`canceled` 事件 |

事件载荷只包含 `trace_id`、`plan_ref`、标准 `TaskStatus`、步骤与预算计数、已由终态投影提供的 state reference、cursor identity 和 Journal sequence。它明确排除任务文本、prompt、working memory、artifact、工具参数、模型输出、错误详情和 approval payload。由于事件与预算对象均为 frozen dataclass，订阅器无法通过引用改写其他订阅器观察到的数据。

默认故障策略为 `fail_open`：一个日志、SSE 或遥测订阅器不可用时会记录结构化警告，但不会改变 Agent 的业务结果。对合规审计等必须交付的部署，Profile 可选择 `fail_closed`，以贡献 ID 和事件类型获得可归因的失败。注册表拒绝重复 ID，并按 `(priority, id)` 产生确定性顺序；复合发布器在 Profile boot 后冻结该快照，因此后续注册不影响已装配 runtime。

## 调用路径

```text
Profile / bundle
  └─ subscriber registry seam
       ├─ logging / SSE / audit contributor plugins
       └─ composite lifecycle publisher
            └─ DeclarativeRuntimeBindings (frozen)
                 └─ CognitiveRuntime.run / resume
                      ├─ publish started / resumed
                      ├─ execute existing declarative driver unchanged
                      └─ publish terminal, failure or cancellation projection
```

该路径与既有 `AgentRunStarted`、`RunResumed`、`AgentRunFinished` durable Journal 事实并行但不重复其职责：前者保持核心审计与恢复真相，新增发布器提供可替换的、事件消费者友好的应用层投影。

## 验收与兼容性

新增测试覆盖确定性顺序、重复 ID 拒绝、运行时冻结、默认 fail-open、严格 fail-closed、默认 logging contributor 的 Profile 接线、终态状态映射，以及 approval payload 和任务内容不泄漏到发布事件。测试还验证默认 Profile 的 capability-plan hash 更新为有意架构演进后的新稳定值。

现有 fixture runtime 无需声明新依赖：它仅获得显式 `NullRuntimeLifecyclePublisher`。生产运行时则必须从已编译 Profile capability closure 解析 `runtime_lifecycle_publisher`，因此不会出现生产环境中的隐式回退或运行期查找。

## References

[1]: https://docs.langchain.com/oss/python/langgraph/interrupts "LangGraph Interrupts documentation"
[2]: https://openai.github.io/openai-agents-python/running_agents/ "OpenAI Agents SDK — Running agents"
