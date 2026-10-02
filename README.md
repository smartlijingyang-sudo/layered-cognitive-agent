# Layered Cognitive Agent（LCA）

LCA 是一个 Python 实现的分层认知智能体框架，目标是主动、持久化的 agent，而不只是对话式 agent。

## 五层架构

| 层 | 职责 | 代表 |
|---|---|---|
| L4 应用/编排 | 极简开发者 API（组合根，唯一允许引用所有下层实现做 DI 组装） | `Agent(...)`、`MultiAgentTeam(...)` |
| L3 Agent 抽象 | Agent 生命周期与团队编排 | `BaseAgent`、`Supervisor`、`TeamOrchestrator` |
| L2 认知运行时 | 核心 Loop | `CognitiveRuntime`、`StrategyRegistry`、Hooks |
| L1 认知组件 | 独立可测试的认知模块 | Brain / Body / Memory / EventBus |
| L0 基础设施 | LLM 适配、工具协议、状态管理 | `LLMAdapter`、`ToolProtocol`、`StateStore` |

层级单向依赖：下层不得反向依赖上层。详见 [ADR-0001](docs/adr/0001-five-layer-separation.md)。

## 入口指引

| 你想找 | 去哪里 |
|---|---|
| 架构决策记录（ADR）索引 | [docs/adr/README.md](docs/adr/README.md) |
| 给编码 agent 的仓库契约（先读） | [AGENTS.md](AGENTS.md) |
| 文档导航与归属 | [docs/specs/documentation-map.md](docs/specs/documentation-map.md) |
| 代码工程守则 | [docs/agent-contract/coding-guardrails.md](docs/agent-contract/coding-guardrails.md) |
| 核心源码 | `lca/`（运行时） · `lca_kernel/`（内核） |
| 测试 | `tests/` |

> 约定：本仓库只收与 LCA 项目本身直接相关的变更；宿主机运维与外部资产归 `~/everything-library`，严禁提交进本 Git（见 AGENTS.md）。
