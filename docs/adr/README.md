# Architecture Decision Records

| ADR | 标题 | 核心决定 |
|---|---|---|
| [0001](0001-five-layer-separation.md) | 五层单向依赖分层 | Accepted |
| [0002](0002-cognitive-loop.md) | 认知闭环 perceive→think→act→observe→reflect→update | Accepted |
| [0003](0003-map-five-module-brain.md) | MAP 五模块 Brain 架构 | Accepted |
| [0004](0004-protocol-first-pluggability.md) | Protocol-First 可插拔设计 | Accepted |
| [0005](0005-composition-root-l4.md) | L4 组合根模式 | Accepted |
| [0006](0006-multi-agent-orchestration.md) | 多智能体团队编排模式 | Superseded |
| [0007](0007-interop-mcp-a2a.md) | 原生互操作协议层（MCP / A2A） | Accepted |
| [0008](0008-framework-positioning.md) | 框架定位与差异化 | Accepted |
| [0009](0009-code-quality-toolchain.md) | 代码质量工具链 | Accepted |
| [0010](0010-component-protocol-exemption.md) | 组件协议豁免规则 | Accepted |
| [0011](0011-simple-prefix-convention.md) | Simple 前缀命名约定 | Accepted |
| [0012](0012-pydantic-migration-assessment.md) | contracts 层维持 dataclass，不迁移到 Pydantic | Accepted |
| [0013](0013-real-llm-e2e-and-scenario-config.md) | 真实 LLM 团队级端到端测试 + 场景配置化 | Accepted |
| [0014](0014-error-classification-and-retry-semantics.md) | 工具错误分类与重试语义 | Accepted |
| [0015](0015-contracts-no-behavior-classes.md) | contracts/ 仅保留类型与接口，参考实现必须放在实现层 | Accepted |
| [0016](0016-contracts-package-v3.md) | 契约层拆包 v3（路径即层次坐标） | Accepted |
| [0017](0017-no-bare-strings-no-any.md) | 禁止裸字符串字面量与裸 Any 类型标注 | Accepted |
| [0018](0018-composition-root-assembly.md) | L4 对象图工厂以 assembly 为准（修订 ADR-0005 措辞） | Accepted |
| [0019](0019-refactor-cleanup.md) | 架构审查后的死代码清理与 Registry 语义统一 | Accepted |
| [0020](0020-map-pipeline-default-and-action-enums.md) | MAP 默认评估管线深化与领域枚举 | Accepted |
| [0021](0021-naming-convention-arbitration.md) | Simple / Default / 领域名命名仲裁与 L3 Agent 改名 | Accepted |
| [0022](0022-map-pipeline-consolidation.md) | MAP 管线收敛为单一 CandidateEvaluationPipeline | Accepted |
| [0023](0023-architecture-deepening.md) | 架构深化——溶解浅模块 + 消除冗余概念 | Accepted |
| [0024](0024-registries-value-object.md) | Registries 值对象取代三个进程级全局单例 | Accepted |
| [0025](0025-role-settlement-retry-and-deadline-clock-domain.md) | 角色结算状态、委派重试与 deadline 时钟域 | Accepted |
| [0026](0026-supervisor-first-class-consultation.md) | Supervisor 一等公民 — ConsultationState + SupervisorReasoner | Accepted |
| [0027](0027-orchestration-families-and-industry-slots.md) | 编排族（Orchestration Family）与业界模式插槽 | Accepted |
| [0028](0028-multi-delegate-routing-and-peer.md) | Multi-delegate、Routing plane、Peer/Swarm | Accepted |
| [0029](0029-closed-object-graph-and-supervisor-mode.md) | 封闭对象图 + SupervisorMode 闭集 + 组合权在 L4 | Accepted |
| [0030](0030-team-domain-language.md) | Team 领域语言（Lead / Coordination） | Accepted |
| [0031](0031-full-chain-telemetry-and-dual-track-tests.md) | 全链路 Telemetry + 双轨 Team 模式测试 | Accepted |
| [0032](0032-delegation-result-ledger-idempotent-delegation.md) | DelegationResult 一等公民 — 路由账本、幂等委派与自描述 span | Accepted |

## 维护规则
- 推翻已有决定时，新建一篇标记 `Supersedes: ADR-XXXX`，不改旧文件
- 这类文档的价值在于记录某一时刻的判断，不在于时刻反映最新状态
- CI `tests/test_refactor_guards.py::test_adr_index_matches_filesystem` 断言本表与 `docs/adr/*.md` 编号集合一致

