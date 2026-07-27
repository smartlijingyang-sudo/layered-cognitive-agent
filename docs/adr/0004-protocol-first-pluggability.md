# ADR-0004: Protocol-First 可插拔设计

## 状态
Accepted

## 背景
框架需要支持：换 LLM 厂商、换记忆后端、换推理策略、加新工具——而不改核心 Loop。传统的继承体系（abstract base class + 子类）耦合度高，且 Python 的 ABC 要求显式继承，不利于第三方接入。

## 决定
所有可替换组件先定义 `@runtime_checkable Protocol`，再给默认实现。当前定义了 22+ 个 Protocol，覆盖：

- **LLM 接入**：`LLMAdapter`（1 个方法 `complete` + `stream`）
- **工具执行**：`ToolProtocol`, `ToolRegistryP`, `SafeExecutorProtocol`
- **认知组件**：`BrainStrategy`, `Body`, `MemorySystem`, `Reasoner`, `Critic`, `DecisionParser`
- **MAP 模块**：`TaskDecomposer`, `StatePredictor`, `StateEvaluator`, `ConflictMonitor`, `TaskCoordinator`
- **运行时**：`Runtime`, `EventBus`, `HookRegistryP`, `Hook`, `StateStore`
- **Agent 层**：`AgentProtocol`, `AgentTransport`

第三方只需实现 Protocol 的方法签名即可接入，无需继承任何基类。`isinstance(obj, Protocol)` 在运行时可检查结构兼容性。

**扩展方式**：写新类实现已有 Protocol → 注册进 Registry → 零风险组合。改已有 dataclass 字段形状 = 改地基，需评估影响面。

## 放弃的方案
- **ABC 继承体系**：要求显式 `class MyImpl(BaseBrain)`，第三方需要 import 框架的基类，耦合度高。
- **鸭子类型无契约**：没有类型检查保障，运行时才发现接口不匹配。Protocol 兼顾了结构子类型的灵活性和编译期可检查的可靠性。

## 后果
- 正面：替换任何组件只需"实现 Protocol + 注册"；Mock 实现作为一等公民支撑离线测试。
- 负面：Protocol 数量多（22+），新贡献者需要理解"哪些 Protocol 对应哪些组件"——通过自动生成的 API 文档（mkdocstrings）缓解。
