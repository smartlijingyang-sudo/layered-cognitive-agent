# Agent Loop 行业基准摘录

调研日期：2026-08-27

## 官方参考

| 来源 | 已核实的运行时能力 | 对本仓库的启示 |
|---|---|---|
| OpenAI Agents SDK 文档 | SDK Runner 负责重复工具调用与分支；在任务结束或等待审批时停止；提供会话、可恢复运行状态、输入/输出/工具守卫、交接和贯穿模型/工具/交接/守卫的追踪。 | 循环应将“停止”和“暂停”明确区别；每个回合应有统一的生命周期钩子和可观测事件，并使策略可通过扩展点组合。 |
| Microsoft AutoGen Termination 文档 | 终止条件是有状态的可组合对象，支持 AND/OR；内置覆盖消息数、文本、令牌、超时、交接、外部停止、工具调用等条件。 | 不能只依赖图节点 visit 上限或单一 StopRule；需引入可组合的、可观测的循环级停止条件，以防止失控循环并支持产品级预算策略。 |
| LangGraph Fault Tolerance 文档 | 重试、尝试级超时和重试耗尽后的错误处理器都与受保护节点直接绑定；超时会取消卡住的尝试，错误处理器接收失败上下文并进入原子化错误路径。 | 本次优先落实图/循环边界已有但未执行的守卫 DSL；将尝试级重试和恢复处理器保留为后续可独立注册的执行器策略，避免在本次把传输或业务重试硬编码进通用解释器。 |

## 初步差距判断

当前仓库已经具有声明式阶段图、阶段贡献、Effect Gateway、审批恢复、Session 回合控制和 StopRule seam。当前通用图解释器在每个阶段后仅依赖节点级 `max_visits`、图的 terminal edge 和 `stop_rule` 所产生的分支；尚未形成一个面向整段 run 的可插件化、可组合、持久化状态化的“循环守卫链”。

优先补齐方向为：在不破坏既有 Phase Executor 与 StopRule 职责的前提下，增加 `LoopGuard` 协议与组合器，拦截每个阶段完成事件，统一实现总步骤限制、wall-clock deadline、外部取消/停止，并以结构化事实、受控结果投影和插件注册接入。这样可将安全与运营约束置于解释器边界，同时保持核心认知阶段及其图拓扑可替换。

## 链接

1. OpenAI, [Agents SDK](https://developers.openai.com/api/docs/guides/agents)。
2. Microsoft, [AutoGen — Termination](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/termination.html)。
3. LangChain, [Fault Tolerance in LangGraph: Retries, Timeouts, and Error Handlers](https://www.langchain.com/blog/fault-tolerance-in-langgraph)。
