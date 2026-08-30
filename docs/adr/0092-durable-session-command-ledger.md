# ADR-0092：持久化 Session 命令账本

## 状态

**Accepted — 2026-08-27**

Amends: [ADR-0073](0073-runsession-sole-session-path.md), [ADR-0078](0078-hil-approval-state-machine.md), [ADR-0090](0090-session-turn-task-controller.md).

## 背景

Session Spine 已以稳定 `session_id`、追加式事实流和 Profile 选择的 `SessionLiveBuilder` 消除生产 `/runs` 对旧 `RunSession.runnable` 的依赖。`ApprovalResolved` 已记录审批恢复的 `command_id`，但 `AgentCommandRouter` 的幂等回执缓存仅存在于进程内。服务重启后，网络重试无法区分“该命令已经完成”与“该命令尚未结算”，因此可能再次恢复相同审批。

主流可恢复 Agent/工作流设计将暂停状态、稳定执行标识和恢复命令作为同一协议：LangGraph 在中断时持久化状态并以同一 thread ID + `Command` 恢复，同时要求中断前副作用幂等；OpenAI Agents SDK 将敏感工具审批作为 run-level interruption；Temporal 要求可重试活动自身幂等，并建议以原子活动隔离副作用。[1] [2] [3]

> 因此，审批恢复的幂等判断必须从 Session durable facts 推导，而不能以 router 的进程内字典作为唯一判断依据。

## 决策

新增 Profile 选择的单值能力 `session_command_ledger`，其公开 Protocol 是 `SessionCommandLedger`。默认 Provider `lca-session-command-ledger` 提供纯 `EventSourcedSessionCommandLedger`：它只折叠一个 Session 的已有事件，不维护第二份可变存储，也不改写 Agent 状态。

| 账本判断 | 事件条件 | 路由动作 |
|---|---|---|
| `PROCEED` | 没有该 `approval_id` 或 `idempotency_key` 对应的 `approval.resolved.v1` | 激活或恢复 LiveAgent，并提交一次恢复命令。 |
| `REPLAY` | 匹配的 `approval.resolved.v1` 后存在 `session.checkpoint.v1` | 不激活 Agent、不重复推进 Loop；返回原结算 checkpoint 的序列号作为命令回执。 |
| `CONFLICT` | 同一 approval 已被不同 command 处理；同一 key 绑定不同意图；或已有 resolve 但没有后续 checkpoint | 写入拒绝事实并返回稳定拒绝原因；禁止重新执行可能带副作用的恢复。 |

命令路由在调用 `SessionActivator.entry_or_recover()` 前先使用 `store_or_load()` 读取事实。这样，已完成重试无需构造进程内对象；不确定窗口（已写决议、未写 checkpoint）会 fail-closed。路由另以 `(session_id, idempotency_key)` 管理短暂的 in-flight future：**相同语义**的并发重试等待同一一次 LiveAgent 调用，**不同语义**的 key 重绑定被立即拒绝。

该设计不增加认知阶段、不改变 Reducer 单写、也不更改 effect idempotency；它仅使 Session 命令的生命周期控制具备与现有 effect gateway 相同的 durable identity 保障。

## 后果

| 维度 | 影响 |
|---|---|
| 可恢复性 | 服务重启后，已结算的相同审批命令从 Journal 重放回执，不重新进入 Agent Loop。 |
| 安全性 | 崩溃发生在 `ApprovalResolved` 与 `SessionCheckpoint` 之间时，系统拒绝恢复而非猜测并重复副作用。该状态需由运维诊断或后续不确定 effect 处理流程结算。 |
| 插件化 | 数据源、查询优化和更严格审计策略可替换 `SessionCommandLedger` Provider；Gateway、AgentRegistry 和 LiveAgent 不依赖具体实现。 |
| 性能 | 默认 JSONL Profile 在命令冷路径读取 Session 事件；后续 Provider 可使用索引化 event store，而无需修改路由。 |

## 验证约束

1. 已结算的审批命令在冷恢复后必须返回同一 `command_id` 与结算 checkpoint 序列号，且不得构造 LiveAgent。
2. 同一审批不能被不同 idempotency key 二次恢复；同一 key 不能绑定不同 payload。
3. 已有审批决议但缺少结算 checkpoint 时必须拒绝，而不能重新调用 Loop。
4. 两个相同的并发审批恢复请求只允许一次 LiveAgent `resume_approval()` 调用。
5. 默认 Profile 必须显式加载 `lca-session-command-ledger`。

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 继续仅使用 `AgentCommandRouter._idempotency` 内存字典 | 进程重启即失效，无法从 durable Session 事实判断重复提交。 |
| 新建命令回执数据库或平行缓存 | 形成第二事实源，并使 Session replay、备份和诊断失去单一入口。 |
| 在 `CognitiveLiveAgent` 中检查历史命令 | 把命令语义和 event query 混入 loop adapter，阻碍替换 Agent Loop。 |
| 对已 resolve 未 checkpoint 的命令直接重试 | 崩溃窗口内可能重复执行外部 effect，违反 fail-closed 和幂等边界。 |

## References

[1]: https://docs.langchain.com/oss/python/langgraph/interrupts "LangGraph Interrupts"
[2]: https://openai.github.io/openai-agents-python/human_in_the_loop/ "OpenAI Agents SDK — Human-in-the-loop"
[3]: https://docs.temporal.io/activity-definition "Temporal — Activity Definition"
