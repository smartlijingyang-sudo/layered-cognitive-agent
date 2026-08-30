# ADR-0091：Profile 选择的会话 Follow-up 调度与可靠队列

## 状态

**Accepted — 2026-08-27**

Amends: [ADR-0073](0073-runsession-sole-session-path.md), [ADR-0088](0088-profile-selected-runtime-factory.md), [ADR-0090](0090-session-turn-task-controller.md)。

## 背景

ADR-0090 为每个已激活 Session 引入了一个可替换的 `SessionTurnController`，从而确保一个 Session 同时最多推进一个 Agent turn，并使取消命令能等待运行任务结算。该机制解决了**任务所有权**，但没有定义用户在运行中追加 follow-up 时的**消息准入与调度策略**。

原有 `Inbox` 在追加后以批量领取方式清空 `next_turn`，而 `CognitiveLiveAgent` 只执行其中第一条消息。与此同时，收件箱事件只有 message ID、没有可恢复载荷。因此第二条并发 follow-up 可能因为 controller 的单活跃限制被拒绝，或在批量领取后不再可从持久事实重建。这与生产 Agent 在实时交互中必须明确处理 concurrent messages 的要求不相容。[1]

> 本决策不添加第七认知阶段，也不改变 `perceive → think → gate → act → reflect → remember → stop`。它只定义 Session 边界的输入准入；已获准的每条消息仍通过同一 Runtime、Reducer、Journal 和 Effect Gateway 执行。

## 决策

新增纯协议 `SessionFollowupPolicy` 与三值 `FollowupDispatch`：`start`、`enqueue`、`reject`。策略只根据 Session 是否已有活动 turn 做确定性准入判断，不能接触 AgentState、Journal、Effect Gateway、审批或 Runtime。`CognitiveLiveAgent` 保留对事实写入、状态迁移和 controller 的唯一所有权。

默认 provider `lca-session-followup-policy` 以 `mode: enqueue` 装配进 base bundle，提供安全 FIFO 排队。部署可通过 Profile 将其切换为 `mode: reject`，使低延迟或严格交互场景在已有运行时直接返回稳定的 `TurnAlreadyRunningError`。`lca-loop-cognitive` 显式要求 `session_followup_policy`，缺少该 capability 时在 Profile boot 阶段 fail-closed，而非退化为隐式默认。

| 边界 | 责任 | 不负责 |
|---|---|---|
| `SessionFollowupPolicy` | 纯粹决定 `start`、`enqueue` 或 `reject` | 启动 task、记录事实、修改 state、执行 effect |
| `CognitiveLiveAgent` | 串行领取 FIFO、执行 turn、写入 lifecycle fact | 硬编码 Profile 的具体策略 |
| `Inbox` | 从 `inbox.spliced.v1` 追加/移除事实恢复未领取消息 | 选择运行时、调用模型或工具 |
| `SessionTurnController` | 单活动 task、协作取消与 idle 屏障 | 消息优先级、消息持久化或调度语义 |
| Profile / Bundle | 选择策略实现和参数 | 在 Gateway 或 Command Router 内写 `if/else` |

`InboxSpliced` 增加可选 `messages` 载荷。append 事实携带紧凑的 `content`、`role` 与 `message_id`；领取操作写入同一事件类型的 remove 事实。Session 重建时仅回放这一事实流，恢复尚未领取的 FIFO 消息。旧事件不含 `messages` 时仍可读取，只是不产生不可恢复的旧式未领取项；这避免引入平行队列表或改变既有事件 type。

执行端在一次领取与下一次空队列判断之间使用会话级 dispatch lock，保证新 follow-up 不会落在排空器刚退出的竞态窗口内。每次只领取一条消息，因而并发追加始终追加到稳定 FIFO 尾部。

## 后果

该机制将实时并发输入显式收敛为可组合的 Session 能力，而不是把排队逻辑藏在 Gateway、controller 或具体 Agent Loop 中。默认 `enqueue` 与业界将排队视为安全默认的做法一致；`reject` 保留最小化的严格模式。[1] OpenAI Agents SDK 也将 run-level 行为、会话、审批和 tool error handling 分开建模，支持将输入/运行策略置于 loop 之外的明确配置面。[2]

当前版本**不提供** `interrupt` 或 `rollback`。这两种策略必须先建立跨进程 checkpoint、effect uncertain/reconcile、补偿与可验证的回滚语义；在真实副作用已发出但 receipt 未稳定时，仅取消 task 不能证明世界状态可回退。长期运行 Agent 的可靠性依赖于 durable execution、checkpoint、lease 和 retry/compensation 等更高层运行时保证。[3]

| 行为 | 默认语义 | 审计事实 | 失败语义 |
|---|---|---|---|
| 空闲 Session follow-up | `start`，立即串行执行 | append + remove + message accepted + turn facts | 执行失败仍由既有 checkpoint 记录 |
| 活动 Session follow-up | `enqueue`，立即返回接收回执 | append，后续 FIFO remove | 不丢弃消息；可在进程重启后重建 |
| 严格 Profile follow-up | `reject`，不写入队列 | 无新收件箱事实 | `TurnAlreadyRunningError` |
| 取消且 `keep_inbox=False` | 终止运行并清空未领取项 | remove + canceled checkpoint | 重启不会复活已清空消息 |

## 验证约束

1. 默认 Profile 必须提供 `session_followup_policy`，且 `lca-loop-cognitive` 将其声明为 required capability。
2. 活动 turn 期间的默认 follow-up 必须立即取得回执，并在当前 turn 结算后以 FIFO 顺序运行一次。
3. 严格策略必须拒绝 follow-up 且不向 durable inbox 写入该消息。
4. 未领取 append 必须可从 JSONL Session replay 恢复；已领取的消息不得在重启后复活。
5. 调度策略不得直接写 Journal、Reducer、AgentState 或 effect；Gateway 与 Command Router 不得依赖具体策略实现。

## References

[1]: https://www.langchain.com/blog/runtime-behind-production-deep-agents "The runtime behind production deep agents — real-time interaction and concurrent-message strategies"

[2]: https://openai.github.io/openai-agents-python/running_agents/ "OpenAI Agents SDK — runner lifecycle, sessions, approvals, and configurable run behavior"

[3]: https://docs.langchain.com/oss/python/langgraph/durable-execution "LangGraph durable execution — persistence, replay, and cross-failure recovery"
