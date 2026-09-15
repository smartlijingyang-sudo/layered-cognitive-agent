# Historical Records

本目录保存已结束工作的计划、研究、执行记录、审计和交付报告。它们用于追溯当时的事实和决策过程，**不是当前系统行为的权威来源**；当前规范、架构决策和操作入口请从 [Documentation Map](../docs/specs/documentation-map.md) 开始。

## 2026-08

| 主题 | 路径 | 内容 |
|---|---|---|
| 架构复核 | [`2026-08/architecture-reviews/`](2026-08/architecture-reviews/) | 实施审计与架构优化总结 |
| ADR-0066 至 ADR-0069 收敛 | [`2026-08/adr-0066-0069-final-cutover/`](2026-08/adr-0066-0069-final-cutover/) | 历史切换计划 |
| ADR-0074 插件化整改 | [`2026-08/adr-0074-plugin-remediation/`](2026-08/adr-0074-plugin-remediation/) | 计划、验收准则、跟踪、执行和完成报告 |
| ADR-0076 闭环 | [`2026-08/adr-0076-closure/`](2026-08/adr-0076-closure/) | 任务计划、事实记录、执行日志与后续计划 |
| 外部研究 | [`2026-08/research/`](2026-08/research/) | Agent 原语、DeepSeek Harness 和框架生态调查 |
| Hermes Agent Loop 对照 | [`2026-08/hermes-agent-loop/`](2026-08/hermes-agent-loop/) | Hermes 核心能力、Agent Loop 映射与无进展工具调用熔断实施记录 |

## 2026-09

| 主题 | 路径 | 内容 |
|---|---|---|
| Think 子图默认切换 | [`2026-09/think-subgraph-default-cutover/`](2026-09/think-subgraph-default-cutover/) | 生产 profile 切到 `phase.think.subgraph_host` 后的验证命令与现场输出 |
| Borrowed Phase-Graph Nodes(PR-3.6 + PR-3.8.x)| [`2026-09/borrow-nodes-pr3.8/`](2026-09/borrow-nodes-pr3.8/) | 7 个 typed-boundary phase-graph 节点(`think.budget.check` / `think.context.compact` / `think.decision.repair` / `act.fanout` / `act.join` / `act.approve.gate` / `act.observe` 合并)的设计稿与单 PR 计划 |

新的过程性材料应在工作结束时进入 `history/YYYY-MM/<topic>/`。若其中结论仍然约束当前代码，应将结论提炼到 ADR 或现行规范后再归档原始材料。
