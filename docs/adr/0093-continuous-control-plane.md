# ADR-0093：持续执行控制面

## 状态

**Proposed — 2026-08-27**

依赖：[ADR-0001](0001-five-layer-separation.md)、[ADR-0004](0004-protocol-first-pluggability.md)、[ADR-0037](0037-journal-as-truth.md)、[ADR-0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md)、[ADR-0090](0090-session-turn-task-controller.md)、[ADR-0092](0092-durable-session-command-ledger.md)。

## 背景

当前 LCA 的声明式 Runtime 已能从编译计划执行六阶段认知闭环，并由 Session Spine 处理持久会话、审批恢复与单会话取消。它仍缺少一个执行控制面，用于把时间或外部事件转化为可去重、可租约、可重试的受限 Session 激活。若将这些逻辑塞入 `perceive → think → act → reflect → remember → stop`，会把跨 Session 的资源调度、worker 崩溃恢复和触发去重混入认知语义，破坏闭集与责任边界。

## 决策

引入与 Agent Loop 正交的 **Continuous Control Plane**。它只决定“何时提交或恢复一个已经受 Profile、Budget 与 capability grant 约束的 Session”，不决定该 Session 的认知路径、State、Effect 或审批结果。

| 组件 | 责任 | 必须不做 |
|---|---|---|
| `Trigger` | 将人工、计划、外部事件和重试表达为不可变输入事实 | 直接创建 Brain 或执行工具 |
| `WorkItem` | 绑定触发、Profile/Session、输入、预算来源和最大重试次数 | 存放可变 AgentState 或扩权 grant |
| `WorkQueue` | 持久去重、原子 claim、过期 lease 恢复、dead-letter 状态 | 解释 Cognitive Phase 或运行插件图 |
| `SessionWorkActivator` | 将已租约的工作项转换为 Session Spine 命令 | 访问具体 Runtime、Brain 或 Body |
| `ContinuousControlPlane` | 协调一次 claim → activate → acknowledge/retry | 启动常驻循环、引入第七认知阶段 |

默认实现使用 SQLite 的 `BEGIN IMMEDIATE` 完成单库原子 claim，并将状态限定为 `pending → leased → dispatched`、`leased → retry_wait | dead` 和未租约的 `pending/retry_wait → canceled`。由于 worker 在 `activate()` 成功但确认前崩溃时无法知道外部命令是否已经送达，语义为 **at-least-once activation**；因此激活器必须把 `work_id` 映射为稳定的 Session ID 与 message ID，并由 Session Spine 从 durable inbox facts 确认重复投递。

> `WorkQueue` 只拥有工作调度事实；Session Journal 仍是会话与 Agent 行为的唯一事实源。两者以稳定 `work_id`、Session ID 和命令/消息标识关联，而不共享 live Python 对象。

持续控制面通过 `continuous_control_plane_factory` capability 提供。Profile 可选择数据库路径、lease 时长与重试间隔；替换队列、时钟、触发源或 Session 激活器不需要更改 `GenericPlanInterpreter`、阶段图或 Gateway 载体。

## 后果

该决策使计划任务、Webhook、代码库事件与 worker 重试拥有统一的最小运行时语义，并为后续 Goal Graph、周期调度器、分布式 worker 和 durable effect reconciliation 提供稳定边界。它不承诺实现常驻 daemon、Webhook server、cron 产品接口或跨数据库事务；这些是部署/基础设施插件的职责。

| 收益 | 代价与限制 |
|---|---|
| 触发去重和 worker 竞争可被单元测试、审计和替换 | SQLite 默认适合单机/共享卷，不替代分布式队列 |
| 崩溃后只重试未确认的工作，不让 runtime 持有后台任务 | 激活语义为至少一次，目标命令必须幂等 |
| Profile 控制存储和 lease 策略，认知闭环保持稳定 | daemon、触发源和 Goal 优先级仍需独立 Provider 实现 |

## 验收约束

1. 同一 `trigger_id` 只能产生一个持久 `WorkItem`。
2. 任一时刻一个 work item 只能被一个有效 lease 确认；失效租约可恢复，已确认项不可重领。
3. 所有重试均受 `max_attempts` 上限约束，并可进入 `dead` 状态。
4. worker 取消时必须释放 lease；不得吞掉 `CancelledError`。
5. Session 激活仅通过 `AgentRegistryFacade` 的 typed command 进行，并以稳定 `work_id` 派生 Session/message 标识，重启后不会追加重复 inbox 消息。
6. Continuous Control Plane 不得添加认知阶段、绕过 Effect Gateway、修改 `AgentState` 或扩大 capability grant。

## 参考

[1]: https://docs.langchain.com/oss/python/langgraph/persistence "LangGraph Persistence：checkpoint 与跨运行存储的职责边界"
[2]: https://openai.github.io/openai-agents-python/human_in_the_loop/ "OpenAI Agents SDK：可序列化暂停状态、审批与恢复"
[3]: https://www.anthropic.com/engineering/building-effective-agents "Anthropic：简单可组合 Agent 模式、环境反馈与停止条件"
[4]: ../design/2026-08-26-continuous-agent-architecture-assessment.md "LCA 连续 Agent 架构评估：控制面、工作队列与租约缺口"
