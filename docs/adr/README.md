# Architecture Decision Records

| ADR | 标题 | 核心决定 |
|---|---|---|
| [0001](0001-five-layer-separation.md) | 五层单向依赖分层 | contracts → L0 → L1 → L2 → L3 → L4，import-linter 自动守卫 |
| [0002](0002-cognitive-loop.md) | 认知闭环 | perceive→think→act→observe→reflect→update，Loop <25 行 |
| [0003](0003-map-five-module-brain.md) | MAP 五模块 Brain | TaskDecomposer/StatePredictor/StateEvaluator/ConflictMonitor/TaskCoordinator（已被 [0022](0022-map-pipeline-consolidation.md) 取代） |
| [0004](0004-protocol-first-pluggability.md) | Protocol-First 可插拔 | 22+ Protocol，第三方实现接口即可接入 |
| [0005](0005-composition-root-l4.md) | L4 组合根 | defaults.py 唯一引用所有具体类的组装点 |
| [0006](0006-multi-agent-orchestration.md) | 多智能体编排 | hierarchical/sequential/graph/debate 可切换（已被 [0019](0019-refactor-cleanup.md)/[0021](0021-naming-convention-arbitration.md) 取代） |
| [0007](0007-interop-mcp-a2a.md) | 原生互操作协议 | L0 内置 MCP/A2A 适配，协议本身可插拔 |
| [0008](0008-framework-positioning.md) | 框架定位 | 认知可解释性 + 生产级工程能力，同时优先 |
| [0009](0009-code-quality-toolchain.md) | 代码质量工具链 | ruff + mypy + pytest + import-linter + pre-commit + CI |
| [0010](0010-component-protocol-exemption.md) | 组件协议豁免规则 | L0-L3 默认必须声明 Protocol，仅 DI 基础设施和 L4 门面豁免 |
| [0011](0011-simple-prefix-convention.md) | Simple 前缀命名约定 | `Simple<Protocol>` = 最小可行参考实现，docstring 须声明能力边界 |
| [0012](0012-pydantic-migration-assessment.md) | 维持 dataclass 不迁移 Pydantic | contracts 层纯数据容器，mypy 静态检查已足够，运行时验证冗余 |
| [0013](0013-real-llm-e2e-and-scenario-config.md) | 真实 LLM E2E 与场景配置 | `pytest -m real_llm` 独立标记，YAML 驱动团队场景 |
| [0014](0014-error-classification-and-retry-semantics.md) | 错误分类与重试语义 | 工具错误分类 + 结构化重试策略 |
| [0015](0015-contracts-no-behavior-classes.md) | contracts/ 不含行为类 | 具体实现必须放实现层，contracts/ 仅保留 Protocol + dataclass |
| [0016](0016-contracts-package-v3.md) | 契约层拆包 v3 | protocols/ 按层拆分 + mechanisms/types + SharedMemoryTool；保留 layerN 与 ADR-0002 闭环 |
| [0017](0017-no-bare-strings-no-any.md) | 禁止裸字符串与裸 Any | 业务逻辑用枚举/常量；公共 API 禁止裸 Any |
| [0018](0018-composition-root-assembly.md) | L4 对象图工厂以 assembly 为准 | assembly 唯一对象图工厂；defaults 纯注册 |
| [0019](0019-refactor-cleanup.md) | 架构审查清理 | 删 GroupChat/Supervisor 壳类；Registry resolve 语义统一；hooks 文件改名 |
| [0020](0020-map-pipeline-default-and-action-enums.md) | MAP 默认评估管线深化 | 默认 MAP 管线 + 领域枚举（原 ADR-0017，重编号） |
| [0021](0021-naming-convention-arbitration.md) | Simple/Default/领域名三分规则 | L1 Simple* / L2 Default* / L3 领域名或 Simple*；BaseAgent→SimpleAgent |
| [0022](0022-map-pipeline-consolidation.md) | MAP 管线收敛 | 五模块 → 单一 CandidateEvaluationPipeline；Supersedes ADR-0003 |
| [0023](0023-architecture-deepening.md) | 架构深化 | 溶解浅模块 + 消除冗余概念 + 完成 rename + 迁层 |
| [0024](0024-registries-value-object.md) | Registries 值对象取代全局单例 | 三个 get_global_* 删除；TeamOrchestrator/Assembly 显式传递 Registries |
| [0025](0025-role-settlement-retry-and-deadline-clock-domain.md) | 角色结算状态、委派重试与 deadline 时钟域 | settled/done 分类单一函数 + wall-clock 时间工具 + gate 双向仲裁 + role_order 确定性 + 重试留 tracking.py + 删除 poll 死代码 |
| [0026](0026-supervisor-first-class-consultation.md) | Supervisor 一等公民 | ConsultationState 控制面 + SupervisorReasoner 组装期绑定；删除 RoleMode 与扁平 team 字段 |

## 维护规则
- 推翻已有决定时，新建一篇标记 `Supersedes: ADR-XXXX`，不改旧文件
- 这类文档的价值在于记录某一时刻的判断，不在于时刻反映最新状态
- CI `tests/test_refactor_guards.py::test_adr_index_matches_filesystem` 断言本表与 `docs/adr/*.md` 编号集合一致
