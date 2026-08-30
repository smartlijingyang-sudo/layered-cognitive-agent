# Hermes Agent 调研记录（工作笔记）

> 状态：进行中。本文记录已从 Hermes 官方仓库和官方文档核实的事实，供 LCA 插件化设计与最终专题文档使用。

## 已核实来源

| 编号 | 来源 | 核实内容 |
|---|---|---|
| 1 | [Hermes Agent GitHub 仓库](https://github.com/NousResearch/hermes-agent) | 顶层包含 `agent/`、`tools/`、`plugins/`、`skills/`、`cron/`、`gateway/` 等模块，表明其将核心循环、工具、扩展、技能、计划任务及多端接入分别组织。 |
| 2 | [Tools Runtime 官方文档](https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime) | 工具通过模块级 `registry.register()` 自注册；内置、MCP 和插件工具均汇入中央注册表；模型可见 schema 会按 toolset 和可用性过滤。 |

## 工具调用链（官方文档）

```text
模型返回 tool_call
  → run_agent.py 循环
  → model_tools.handle_function_call(...)
  → 循环级工具直接处理（todo / memory / session_search / delegate_task）
    或 plugin pre_tool_call
  → registry.dispatch(...)
  → 同步或异步 handler
  → 结构化结果
  → plugin post_tool_call
  → 回写给模型进入下一轮
```

## 对 LCA 的初步含义

Hermes 的优点是将工具发现、可用性过滤、工具分组与分发集中到一个注册表；但它使用模块导入副作用和全局 registry。LCA 不应复制该实现方式，而应保留本项目的 **Protocol → Seam → Provider / Adapter → Registry → Plugin → Profile / Bundle** 路径、作用域与权限收缩约束。可吸收的是“**把模型可调用工具、运行时特权工具和外部工具分层**”这一思想，并将其落在现有 `agent_loop`、`skills`、`tools` Seam 和 Journal 事件之内。

## 待核实

后续将继续核对 Hermes `run_agent.py`/`agent/conversation_loop.py` 的循环终止、上下文压缩、重复工具调用防护、学习/技能生成、子代理委派与持久状态机制，并映射到 LCA 当前实现及目标架构。

## References

[1]: https://github.com/NousResearch/hermes-agent "NousResearch/hermes-agent"
[2]: https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime "Hermes Agent Tools Runtime"

## 官方 Agent Loop 链路

[Agent Loop Internals 官方文档](https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop) 将 `AIAgent` 定义为一个集中式编排对象：它负责提示词与工具 schema 装配、API 传输模式选择、可取消模型调用、工具执行、会话历史、压缩、重试、模型回退，以及父子代理共享的迭代预算。其一次用户回合的公开链路是：

```text
输入与任务 ID
  → 追加 user message / 构建或复用 system prompt
  → preflight context compression
  → 将统一内部消息投影为 provider wire format
  → 注入临时预算/上下文层并设置 prompt cache
  → 可中断模型请求
  → [tool_calls: 校验、持久化、审批、执行、按原顺序写回 observation、再入]
    [text: 持久化 session、必要时刷新 memory、返回]
```

源码 `agent/conversation_loop.py` 进一步显示，Hermes 在工具副作用发生前先持久化 assistant 的 tool-call turn；若该写入失败，就停止而不是从仅存在于进程内的轨迹执行工具。工具分支还包括 tool-call ID 去重、名称修复和校验、JSON 校验、并发批处理、执行后压缩，以及迭代/输入/墙钟预算和中断、失败回退、传输重试等边界处理。

## 技能与学习闭环

[Skills System 官方文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) 确认：技能是按需加载的知识文档，采用渐进披露；目录先以紧凑清单形式提供，随后按需读取完整 `SKILL.md` 或其中的引用文件。`/learn` 将文档、代码库、会话操作或说明变成可复用的技能；其写入仍经 `skill_manage`，因此会服从技能写入审批。

这给 LCA 的可吸收点是：把 **候选技能目录 → 按需激活 → 受审批的候选升级** 作为 Memory/Context Lifecycle/Act 的组合，而不是把学习或技能创建塞进认知循环的额外阶段。与 LCA 宪法一致的完成形态应是：终态事实触发的旁路复盘只生产候选；技能读取由 Perceive/Context Manifest 选择；写入必须经 Effect Gateway、Approval、Journal 与 Reducer 路径。

## 当前 LCA 基线复核

现有 `docs/design/2026-08-27-hermes-agent-loop-plugin-gap-closure.md` 和 `ad10b6da` 已实现“终态 lifecycle 事件 → 幂等 review ticket → candidate-only assessment”的第一段。当前主线仍缺少一项能把此机制变为**可在重启后处理的持久队列能力**：review ticket 仅是进程内/服务内待领取工作时，连续运行场景无法证明终态学习复盘不会丢失。后续实现应使用新的窄 `LearningReviewTicketStore` Protocol 和 SQLite provider，把 ticket 的创建、幂等去重与 claim/settle 转化为 Journal 可引用的耐久事实；学习服务仍不得直接写已安装 skill 或 profile。

[3]: https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop "Hermes Agent — Agent Loop Internals"
[4]: https://hermes-agent.nousresearch.com/docs/user-guide/features/skills "Hermes Agent — Skills System"
