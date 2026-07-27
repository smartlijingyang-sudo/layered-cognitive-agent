# Architecture Decision Records

| ADR | 标题 | 核心决定 |
|---|---|---|
| [0001](0001-five-layer-separation.md) | 五层单向依赖分层 | contracts → L0 → L1 → L2 → L3 → L4，import-linter 自动守卫 |
| [0002](0002-cognitive-loop.md) | 认知闭环 | perceive→think→act→observe→reflect→update，Loop <25 行 |
| [0003](0003-map-five-module-brain.md) | MAP 五模块 Brain | TaskDecomposer/StatePredictor/StateEvaluator/ConflictMonitor/TaskCoordinator |
| [0004](0004-protocol-first-pluggability.md) | Protocol-First 可插拔 | 22+ Protocol，第三方实现接口即可接入 |
| [0005](0005-composition-root-l4.md) | L4 组合根 | defaults.py 唯一引用所有具体类的组装点 |
| [0006](0006-multi-agent-orchestration.md) | 多智能体编排 | hierarchical/sequential/graph/debate 可切换 |
| [0007](0007-interop-mcp-a2a.md) | 原生互操作协议 | L0 内置 MCP/A2A 适配，协议本身可插拔 |
| [0008](0008-framework-positioning.md) | 框架定位 | 认知可解释性 + 生产级工程能力，同时优先 |
| [0009](0009-code-quality-toolchain.md) | 代码质量工具链 | ruff + mypy + pytest + import-linter + pre-commit + CI |

## 维护规则
- 推翻已有决定时，新建一篇标记 `Supersedes: ADR-XXXX`，不改旧文件
- 这类文档的价值在于记录某一时刻的判断，不在于时刻反映最新状态
