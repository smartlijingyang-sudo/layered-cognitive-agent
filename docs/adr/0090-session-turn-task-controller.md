# ADR-0090：会话级 Turn Task Controller

## 状态

**Accepted — 2026-08-27**

Amends: [ADR-0073](0073-runsession-sole-session-path.md), [ADR-0078](0078-hil-approval-state-machine.md), [ADR-0088](0088-profile-selected-runtime-factory.md).

## 背景

`Session Spine` 已经把 Agent Loop 的选择收敛为 Profile 提供的 `agent_loop` 与 `runtime_factory`，但 LiveAgent 的取消此前仅改写本地状态标记。运行中的 `Agent.run()` / `Agent.resume()` 任务并不归 Session 所有，也没有被取消命令等待。这会让长程工具调用、审批等待和 `/runs` 兼容载体产生“已取消但仍在执行”的竞态。

业界实践表明，**可恢复的 Agent 会话必须同时拥有稳定会话标识、持久化状态边界和明确的中断/恢复操作**。LangGraph 将中断与持久化检查点绑定，并要求以相同 thread 标识恢复；OpenAI Agents SDK 则将 tools、guardrails、handoff 和 session 置于 Runner 管理的单次运行生命周期中。[1] [2]

> 本 ADR 不增加第七个认知阶段，也不创建新的取消事件词表。取消是 Session 对正在执行 Turn 的生命周期控制；六阶段 `perceive → think → act → reflect → remember → stop` 保持不变。

## 决策

新增两个纯 Protocol：`SessionTurnController` 与 `SessionTurnControllerFactory`。每个已激活 Session 由 Profile 解析 `session_turn_controller_factory`，并为其创建一个隔离的任务控制器。默认 Provider 是 `lca-session-turn-controller-factory`，使用进程内 `asyncio.Task`；远程 worker、耐久工作流或分布式执行器可替换该 Provider，而不改 Gateway、Command Router、Session Store 或具体 Agent Loop。

| 边界 | 责任 | 明确不负责 |
|---|---|---|
| `SessionTurnController` | 单 Session 单个 in-flight task、协作取消、`when_idle()` | Journal、Reducer、Agent 状态写入 |
| `CognitiveLiveAgent` | 调用 Loop、记录 Turn/Checkpoint、把取消映射为 durable 终态 | 直接创建或管理裸 `asyncio.Task` |
| `CommandGateway` / `AgentCommandRouter` | 提交 typed CancelCommand，并等待 LiveAgent 结算 | 感知具体 Loop 或 task 实现 |
| `SessionStore` | 追加既有事实并支持恢复 | 保存 live task 或 Python 对象 |
| Profile / Bundle | 选择 Controller Provider | 在 Gateway 内硬编码实现选择 |

默认控制器拒绝同一 Session 的并发 Turn，并在 `cancel()` 返回前等待活动任务完成清理。`LiveAgent.cancel()` 升格为 awaitable；因此取消回执只会在任务已停止、`TurnEnded(reason="canceled")` 与 `SessionCheckpoint(status="canceled")` 已写入后返回。若取消发生在审批等待期，既有 `approval.persisted` 事实继续用于审计，但 terminal checkpoint 优先并使其不再可恢复为待审批状态。

## 后果

运行任务是**可替换的 Session 资源**，而不是 Gateway 的后台实现细节，也不是 `CognitiveRuntime` 的隐式责任。完整 Loop 仍由 ADR-0088 的 `runtime_factory` 选择；本 ADR 仅提供其运行期任务所有权，保持“稳定内核 + Profile 组合 Provider”的插件化结构。

该设计沿用已存在的 `TurnEnded` 和 `SessionCheckpoint` 作为恢复事实，避免平行事件模型。它也使未来的耐久 worker Provider 能以同一 Protocol 挂接：只要实现单活跃 Turn、取消确认和空闲屏障，即可替换默认实现。

## 验证约束

1. 默认 Profile 必须显式提供 `session_turn_controller_factory`，而 `lca-loop-cognitive` 必须声明该 capability 为 required。
2. 同一 Session 的第二个执行操作必须以稳定错误拒绝，不能与第一操作并发推进。
3. 取消活跃 Turn 后，调用方必须观察到被取消的运行任务、唯一的 canceled checkpoint 和可恢复的 `DISPOSED` 生命周期。
4. 取消待审批 Session 后，恢复只能得到 `DISPOSED`，不能残留无效的 pending approval。
5. Command Router、Gateway 与 Runtime Assembly 不得导入默认任务控制器的具体实现。

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 在 Gateway / SessionRunAdapter 直接保存并取消 task | 让 carrier 获得 Loop 运行时所有权，破坏 Gateway 纯载体边界。 |
| 复用 legacy `RunRegistry` / `RunSession.task` | 将旧的内存事实模型重新引入 Session Spine，无法实现单一路径恢复。 |
| 在 `CognitiveRuntime` 内部维护 task | Runtime 无法代表 Session 命令生命周期，且替换完整 Loop 时会复制同一逻辑。 |
| 只设置 LiveAgent 的 canceled 标记 | 不能停止已经开始的工具、模型或恢复任务；回执与真实运行状态会不一致。 |

## References

[1]: https://docs.langchain.com/oss/python/langgraph/interrupts "LangGraph Interrupts — checkpointed pause and resume"

[2]: https://openai.github.io/openai-agents-python/agents/ "OpenAI Agents SDK — runner-managed agent lifecycle"
