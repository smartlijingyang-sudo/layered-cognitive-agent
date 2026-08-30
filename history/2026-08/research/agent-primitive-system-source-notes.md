# Agent 原语体系外部来源笔记

**日期：** 2026-08-21
**用途：** 为《Agent 原语体系宪章》和 ADR-0069 保存用于完整性校验的外部框架与研究来源。本文不是系统规范；系统规范以 `docs/design/2026-08-21-agent-primitive-system-constitution.md` 为准。

## OpenAI Agents SDK

OpenAI 的 Agents SDK 指南把 Agent 描述为能够计划、调用工具、跨 specialist 协作并维持足以完成多步工作的状态的应用。其文档目录将 agent definitions、models / providers、agent loop 与 streaming、sandbox、handoffs、guardrails / human review、results / resumable state、tools / MCP、tracing 与 evaluation 分开。这支持将身份意图、运行时、协作、控制、执行、状态、互操作和证据视为独立变化维度，而不是一个“agent”类的属性。[1]

## Anthropic 的可组合模式

Anthropic 将固定 code path 的 workflow 与由 LLM 动态主导过程和工具使用的 agent 区分；文章将 augmented LLM 的 retrieval、tools、memory 视为基础能力，并列出 prompt chaining、routing、parallelization、orchestrator-workers、evaluator-optimizer 和 autonomous agent 等可组合模式。文章强调简单可组合、透明的计划过程、仔细设计的 Agent-Computer Interface，以及只有在复杂度带来实际收益时才增加系统复杂度。[2]

## LLM Agent 规划研究

《Understanding the planning of LLM agents: A survey》提出 LLM agent planning 的分类包括 Task Decomposition、Plan Selection、External Module、Reflection 和 Memory。它支持在原语体系中把 planning、selection、外部能力、reflection 与 memory 分为可独立声明的贡献，而不是合并为“reasoner”。[3]

## Google ADK Memory

Google ADK 文档将单一会话的 events / temporary state 与可跨会话检索的 long-term knowledge 区分，并将 memory ingestion、event delta ingestion、explicit memory entry 和 search memory 定义为不同操作。这支持将 facts、working state、memory、knowledge source 和 retrieval 分为不同对象和生命周期。[4]

## 参考

[1]: https://developers.openai.com/api/docs/guides/agents "OpenAI Agents SDK guide"
[2]: https://www.anthropic.com/engineering/building-effective-agents "Anthropic: Building effective agents"
[3]: https://arxiv.org/abs/2402.02716 "Understanding the planning of LLM agents: A survey"
[4]: https://adk.dev/sessions/memory/ "Google ADK Memory"
