# Hermes Agent：核心能力与 Agent Loop 研究

**研究日期：** 2026-08-27
**范围：** Nous Research 官方架构概览与 Agent Loop 开发文档。本文记录外部系统的事实，不改变 LCA 当前规范。

## 核心能力

Hermes 的中心对象是 `run_agent.py` 中的 `AIAgent`。官方文档将其描述为集中承担提示词与工具 schema 组装、Provider/API 模式选择、可中断模型调用、工具调度、对话历史维护、压缩/重试/后备模型、父子代理迭代预算，以及上下文丢失前的记忆落盘。其入口覆盖 CLI、Gateway、ACP 和 Python 集成；内部统一到 OpenAI 风格消息格式，再由适配器支持 `chat_completions`、`codex_responses`、`anthropic_messages` 三种 Provider API 模式。[1] [2]

| 能力域 | Hermes 的机制 | 对 LCA 的启示 |
|---|---|---|
| Provider 适配 | 三种 API mode 在调用前后收敛为内部消息格式；按显式参数、Provider、URL 启发式和默认值决议。 | 将 Provider 边界保持为可替换 Adapter，避免泄漏到运行循环。 |
| 对话与会话 | SQLite + FTS5 持久化会话，支持检索和血缘。 | 用 Journal/Checkpoint 维持事实、状态与恢复边界的清晰所有权。 |
| 工具 | Registry 发现 schema 和 handler；单调用顺序执行，多调用并发，交互式工具强制串行，按原始顺序回填结果。 | 并发只应属于 Body/SafeExecutor 的策略，回填和审计必须确定性。 |
| 人机控制 | 危险工具经 approval callback；API 调用可由新消息、停止命令或信号中断。 | 审批、取消和幂等应通过控制面和 Execution Envelope，而非散落回调。 |
| 长程上下文 | 预检压缩、Provider prompt caching、上下文压力提示、记忆预刷新。 | 将预算、检索、压缩和提示渲染收敛为 Perceive/Memory 内部策略。 |
| 自我改进 | 通过技能、记忆、轨迹和子代理形成经验复用闭环。 | 把学习的输入/产出放入 Journal 与 Memory Policy，保留可追溯性。 |

## 官方 Agent Loop 链路

每次 `run_conversation()` 迭代依次：生成任务 ID、写入用户消息、构建或复用系统提示、在上下文超过阈值时预压缩、基于会话记录生成目标 API 所需 messages、注入短生命周期预算/压力提示、按 Provider 加入缓存标记，然后以可中断方式调用模型。若模型返回工具调用，系统执行工具、将结果回填消息历史并回到构造请求步骤；若返回文本，持久化会话、按需要刷新记忆并返回终答。[1]

```text
input / resume
  → task identity + durable conversation
  → prompt + tool schema assembly
  → preflight context compression / ephemeral budget layer
  → provider-mode conversion + interruptible LLM call
  → response parse
      ├─ tool calls → approval / dispatch / ordered tool results → next LLM turn
      └─ final text → persistence + memory flush → outcome
```

工具分派前会触发前置插件 hook，并对危险命令走审批；分派后触发后置 hook。`todo`、`memory`、`session_search` 与 `delegate_task` 被 `AIAgent` 直接截获，因其修改 agent-local state；普通工具才进入 Registry。此设计易于使用，但将多个跨域职责集中进大型编排类，且把部分状态修改留在循环内。[1]

## 初步对齐判断

Hermes 的优势是把实际产品需要的 Provider 兼容、可中断执行、并发工具、压缩、持久化、审批、记忆和子代理连接为一条可工作的循环。LCA 不应复制其单一巨型 `AIAgent` 或在闭集外增加阶段；应将上述能力分别映射至既有 **Perceive、Think、Gate、Body、Reflect、Remember、Stop** 及 Journal/Composition 横切系统，并用 `Protocol → Seam → Provider/Strategy → Registry → Plugin → Profile` 装配。这样既获得 Hermes 的可用性，又维持 LCA 的双平面、Reducer 单写入、Journal 事实源与循环闭集约束。

## 参考资料

[1] [Hermes Agent — Agent Loop Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop)
[2] [Hermes Agent — Architecture](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture)

## Hermes 插件面与 LCA 的取舍

Hermes 同时提供原生 `plugin.yaml` + `register(ctx)` 插件、Python `register_*` 扩展 API、配置驱动 Provider、目录式事件 Hook、MCP、技能源和 Agent Plugins v1 兼容包。原生插件可注册工具、生命周期 Hook、斜杠命令、技能和 CLI 子命令；第三方插件可从用户目录、项目目录或 Python entry point 发现。文档强调 API 按增加式兼容，Hook payload 用关键字字段扩展，并按回调签名过滤兼容旧插件。[3]

其 portable package 对包位置、路径、符号链接、`plugin.json`、技能前言和 MCP 配置做本地验证，并在局部组件错误时跳过该边界而继续加载有效同级组件；但官方也明确指出该规范不定义信任、权限、来源或 sandbox，启用即与本地原生插件采用同等完全信任模型。[3]

这为 LCA 的补强确定了方向：保留 Hermes 的**可移植、可发现、局部容错、资源隔离目录和能力分类型**优势，但不可沿用自由 Hook 对循环 State/Decision 的直接修改。LCA 应以现有 Manifest 的 `requires/provides/layer/kind/effects/test_suite` 和 Profile DAG 装配为权威；新能力通过明确 seam 和 typed provider 接入，循环控制只由 Runtime 与既有 Reducer/Body 窄门承担。

[3] [Hermes Agent — Build a Hermes Plugin](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)

## 源码复核（官方仓库快照）

在 2026-08-27 拉取的 `NousResearch/hermes-agent` 主分支快照中，`run_agent.py` 的公开 `AIAgent.run_conversation()` 主要负责跨进程会话租约、运行级可观测性上下文与最终资源释放，并将核心循环委派给 `agent/conversation_loop.py`。核心循环在每个用户回合先构建 `TurnContext`，其中汇集输入净化、待办/提示恢复、系统提示、预检压缩、插件 `pre_llm_call`、外部记忆预取与崩溃恢复持久化；然后在 **API 次数与共享 iteration budget** 均允许的条件下持续循环。

每一轮先处理 redirect、中断、审阅预算与 iteration budget，再修复消息交替、构造请求副本、注入仅请求期上下文、选择 Context Engine、净化孤立工具消息、统一 tool-call JSON、应用 Provider cache 装饰并重新评估压缩压力。成功模型响应若含工具调用则交给批处理计划器；该计划器按相邻调用切分为可并发安全段与顺序屏障段，既尽量并发读操作，又维护交互式、未知或副作用工具的顺序。顶层委派一律转为后台子代理，其完成结果作为新消息重新进入会话；子代理内部编排则保持同步以便汇总。该组合确认 Hermes 的主要实现形态是“功能强但集中式循环 + 全局 Hook/回调面”。[4]

对 LCA 而言，可直接吸收的需求是：**预算与取消、请求期上下文选择/压缩、请求适配、工具批次执行策略，以及子代理结果的有序回注**。它们都应成为已有原语内的 provider 或 strategy，而不能成为新的循环阶段或允许 Hook 跨越脑手边界改写 State。

[4] [NousResearch/hermes-agent — `run_agent.py` 与 `agent/conversation_loop.py`](https://github.com/NousResearch/hermes-agent)
