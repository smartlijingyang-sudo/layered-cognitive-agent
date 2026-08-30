# ADR-0001: 五层单向依赖分层

## 状态
**Superseded by [ADR-0104](0104-semantic-layer-rename.md)** — 层名从 `layer0/1/2/3/4` 改为语义化名称（`infrastructure`/`cognition`/`runtime`/`agent`/`application`）。本 ADR 保留作为历史档案；新增代码与文档请以 ADR-0104 为准。

## 原始状态
Accepted

## 背景
Agent 框架需要在"上手简单"和"深度可定制"之间取得平衡。如果所有代码混在一起，新增功能会牵一发动全身；如果拆得太细，开发者连 `Agent(...)` 三行代码都写不出来。

## 决定
框架自上而下分为 5 层，层间只允许上层调用下层的协议接口：

| 层 | 职责 | 典型内容 |
|---|---|---|
| L4 应用/编排 | 极简开发者 API | `Agent(...)`, `MultiAgentTeam(...)` |
| L3 Agent 抽象 | Agent 生命周期与团队编排 | `BaseAgent`, `Supervisor`, `TeamOrchestrator` |
| L2 认知运行时 | 核心 Loop（<25 行） | `CognitiveRuntime`, `StrategyRegistry`, Hooks |
| L1 认知组件 | 独立可测试的认知模块 | Brain/Body/Memory/EventBus |
| L0 基础设施 | LLM 适配、工具协议、状态管理 | `LLMAdapter`, `ToolProtocol`, `StateStore` |
| contracts | 纯数据契约 + Protocol 定义（被所有层依赖） | dataclass, Protocol |

**铁律**：任意一层只能调用直接下方一层暴露的协议接口；跨层直接调用视为架构违规。由 `import-linter` 在 CI 中自动执行。

**L4 作为组合根**：`application/defaults.py` 是唯一允许引用所有下层具体实现类的地方，负责 DI 组装。下层不得反向依赖 L4。

## 放弃的方案
- **三层（API/Core/Infra）**：粒度太粗，Brain 和 Memory 被塞在同一层，无法独立替换和测试。
- **六层以上（每模块一层）**：过度碎片化，增加 import 路径长度和理解成本，对单人/小团队项目不划算。

## 后果
- 正面：每层可独立演进、独立测试；新增一种记忆实现只需改 L1，不影响 L2/L3。
- 负面：组合根（L4）需要引用所有层的具体类，如果框架规模增长到需要多个组合根，需要重新评估这个模式。
