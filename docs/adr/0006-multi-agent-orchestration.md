# ADR-0006: 多智能体团队编排模式

## 状态
Accepted

## 背景
单个 Agent 能力有限，复杂任务需要多个 Agent 协作。问题是：团队编排应该是固定的还是可切换的？

## 决定
`TeamConfig.process` 字段使用 `Literal` 类型，支持多种编排模式：

| 模式 | 说明 |
|---|---|
| `hierarchical` | Supervisor 统一分配任务、收集结果 |
| `sequential` | 成员按顺序依次执行 |
| `graph` | 预留：基于 DAG 的自定义工作流 |
| `debate` | 预留：多 Agent 辩论达成共识 |

`TeamOrchestrator` 根据 `process` 字段选择编排策略。新增编排模式只需在 Orchestrator 里加一个私有方法分支（不改已有分支），契合开闭原则。

Agent 间委派通过 `DelegationSpec`，支持 `internal`（框架内直接调用）、`a2a`（跨框架 A2A 协议）、`mcp`（MCP 协议）三种通信方式。

## 放弃的方案
- **只做一种编排模式**：不同场景需要不同协作模式（研究团队适合 hierarchical，流水线适合 sequential）。
- **完全图编排（如 LangGraph）**：灵活但学习曲线陡。作为 `graph` 模式的底层实现接入，不替代简单的 hierarchical/sequential。

## 后果
- 正面：`MultiAgentTeam(members, process="hierarchical")` 一行组建团队；新增编排模式不影响已有代码。
- 负面：当前 `sequential` 是纯顺序执行，缺少并行 fan-out（scatter-gather）——后续可通过 `asyncio.gather` 补充，不改 Protocol。
