# Documentation Map

本页是 LCA 文档的导航入口。目录归属和维护规则由 [Documentation Standard](../AGENTS.md) 定义。

| 需求 | 权威位置 | 说明 |
|---|---|---|
| 了解开发约束、仓库地图和验证命令 | [根 AGENTS.md](../../AGENTS.md) | 每次开发会话的高频入口 |
| 查询术语、数据所有权和结构化认知模型 | [LCA structured cognition guide](lca-structured-cognition-guide.md) | Fact、State、Decision、Verdict、Effect、Journal 等词汇 |
| 查询现行协议与操作说明 | `docs/specs/` | Harness、阶段图、运行时投影、工具恢复、命名与包组织规范、集成规范 |
| 查询包目录规模、命名与拆分规则 | [package-organization-discipline.md](package-organization-discipline.md) | 8/10/15 规则、概念群映射、代码体量硬约束 |
| 查询命名宪法（目录/文件/类/函数/变量/枚举全维度） | [naming-constitution.md](../design/naming-constitution.md) | v3 九群归属、四维分解、角色后缀强制词表 |
| 查询不可变的架构决策及其状态 | [ADR index](../adr/README.md) | Accepted、Proposed、Superseded、Deprecated 决策 |
| 查询宪法级设计与长期模型 | `docs/design/` | 认知原语、声明式插件、时空和运行计划设计 |
| 查询 Journal、Trace 和运行诊断 | `docs/observability/` | 可观测性子系统规格和调试手册 |
| 查询角色库、技能包和部署组件说明 | `roles/`、`skills/`、`deploy/` | 与所属组件共同维护的就近文档 |
| 查询已结束实施、研究和审计的原始记录 | [history](../../history/README.md) | 非现行、仅供追溯的过程材料 |

## 维护边界

将新内容放入已有的权威家。当前系统如何工作，写入 `docs/specs/` 或 `docs/observability/`；为什么选择某种结构，写入 ADR；仅在长期设计仍有独立价值时更新 `docs/design/`。实施计划、调查笔记、进度、验收日志和优化报告在结束后归档到 `history/YYYY-MM/<topic>/`，不再进入仓库根目录或 `docs/`。
