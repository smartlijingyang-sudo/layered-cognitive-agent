# 业界 Agent 架构对照要点

## LangGraph 官方概览
来源：https://docs.langchain.com/oss/python/langgraph/overview

LangGraph 被定位为低层级的 Agent 编排框架和运行时，面向长时间运行、有状态的 Agent；支持在同一图中混合确定性、手写步骤与 LLM 驱动步骤。官方强调 durable execution、streaming、human-in-the-loop、memory、可观测性和生产部署。LangGraph 不抽象 prompts 或固定架构，而是提供 graph orchestration runtime。

## Microsoft Agent Framework 官方概览
来源：https://learn.microsoft.com/en-us/agent-framework/overview/

Microsoft Agent Framework 官方概览将 workflows 定义为以显式执行路径连接 agents 和 functions 的 functional/graph-based workflows，并将 integrations 分为模型提供商、agent services、tools、context providers、middleware、evaluation services 与 UI frameworks 等组件。

## 初步判断

业界已普遍出现“图工作流 + 可组合能力 + 持久状态 + 人工介入 + middleware/guardrails”的组合，但多数框架的插件边界更偏组件/工具/中间件，未必把 capability manifest、计划编译、control slots、effect policy、Reducer 单写和 evidence provenance 全部统一到一份内核运行合同中。

## OpenAI Agents SDK 官方指南
来源：https://developers.openai.com/api/docs/guides/agents

OpenAI Agents SDK 的 Runner 负责 tool loop、handoff 后切换 agent，并在运行完成或等待审批时停止；SDK 还提供 input/output/tool guardrails 与可恢复审批流。官方定位更接近由 SDK 管理生命周期的 Agent loop，而不是完全开放的通用运行时内核。

## Microsoft Agent Framework Middleware
来源：https://learn.microsoft.com/en-us/agent-framework/concepts/agents/middleware/

Microsoft Agent Framework 提供 Agent Run、Function Calling 和 IChatClient 三类 middleware，可拦截、检查、修改输入输出，并通过 next callback 串成链。其扩展模型明显覆盖横切关注点，但更偏 middleware chain，而非把控制投稿编译到类型化阶段图和运行计划。

## 更新判断

LCA 与 LangGraph 的相似处在于低层图编排、状态、恢复与人工介入；与 OpenAI Agents SDK 的相似处在于统一 Runner、工具循环、handoff、guardrails 和审批暂停；与 Microsoft Agent Framework 的相似处在于能力集成与横切 middleware。LCA 的差异点是把这些能力进一步统一为显式 Manifest、capability graph、phase/control/effect plan、Reducer 和 evidence provenance。
