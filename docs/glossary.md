# LCA Framework 术语表（Glossary）

> 本文件是框架领域术语的**唯一真理来源**。任何 ADR、代码 docstring、PR 描述中的术语一旦与本文冲突，以本文为准。
> 新增领域术语必须先在此登记，再由 PR 引用。

---

## 架构层

| 术语 | 定义 |
|---|---|
| **Contracts** | 纯数据契约层（`lca/contracts/`），定义所有 Protocol 接口与 DTO 数据类，不依赖任何实现层 |
| **Layer 0 (L0)** | 基础设施层（`lca/layer0_infra/`），提供 LLM 适配器、传输协议、注册表、状态存储等可替换基础设施 |
| **Layer 1 (L1)** | 认知组件层（`lca/layer1_cognitive/`），实现 Brain、Body、Memory 等认知能力模块 |
| **Layer 2 (L2)** | 运行时层（`lca/layer2_runtime/`），包含核心认知循环 `CognitiveRuntime` 与 Hook 机制 |
| **Layer 3 (L3)** | Agent 抽象层（`lca/layer3_agent/`），定义 BaseAgent、Supervisor、TeamOrchestrator 及编排策略 |
| **Layer 4 (L4)** | 组合根层（`lca/layer4_app/`），唯一允许 import 所有具体类的组装点，提供开发者 API |

## 认知循环

| 术语 | 定义 |
|---|---|
| **CognitiveRuntime** | 核心认知循环实现，perceive → think → act → observe → reflect → update 六步闭环 |
| **Hook** | 生命周期钩子，注册在 HookRegistry 中，在认知循环各阶段触发，用于注入横切关注点 |
| **HOOK_NAMES** | 12 个预定义钩子名称常量：on_start, pre/post_perceive, pre/post_think, pre/post_act, pre/post_reflect, on_error, on_pause, on_complete |

## Brain 与 MAP 五模块

| 术语 | 定义 |
|---|---|
| **ModularBrain** | BrainStrategy 的默认实现，串联 MAP 五模块 + Reasoner + Critic + DecisionParser |
| **MAP 五模块** | Model-Action-Perception 五模块：TaskDecomposer、StatePredictor、StateEvaluator、ConflictMonitor、TaskCoordinator |
| **Reasoner** | 候选方案生成器，调用 LLM 产生推理候选 |
| **DecisionParser** | 将 LLM 原始输出解析为 StructuredDecision |
| **Critic** | 基于 Observation 生成 Reflection（on_track / needs_correction / blocked） |
| **TaskDecomposer** | 将任务分解为子任务列表 |
| **StatePredictor** | 预测某候选动作执行后的状态变化 |
| **StateEvaluator** | 对预测状态打分 |
| **ConflictMonitor** | 检测候选方案间的冲突 |
| **TaskCoordinator** | 在多候选方案间做最终仲裁，选出唯一 StructuredDecision |

## Body 与执行

| 术语 | 定义 |
|---|---|
| **SimpleBody** | Body 协议的默认实现，按 action_type 分发到 respond / use_tool / delegate / handoff |
| **SafeExecutor** | 工具安全执行器，封装权限检查、缓存、重试逻辑 |
| **ToolRegistry** | 工具注册表，按名称查找已注册的 Tool |

## 记忆系统

| 术语 | 定义 |
|---|---|
| **MemorySystem** | 四层记忆协议：working / semantic / episodic / procedural |
| **SimpleMemorySystem** | MemorySystem 的默认实现，内存级四层存储 + 可选共享绑定 |
| **TeamSharedMemoryStore** | 跨 Agent 共享记忆存储，只允许 semantic / procedural 层共享（CoALA 语义边界） |
| **MemoryRecord** | 记忆记录 DTO，含 memory_type、importance、embedding 等字段 |

## 编排与团队

| 术语 | 定义 |
|---|---|
| **OrchestrationStrategy** | 编排策略协议，每种 process 模式对应一个实现 |
| **HierarchicalStrategy** | Supervisor 单向委派、汇总 |
| **SequentialStrategy** | 流水线式顺序传递 |
| **ParallelStrategy** | scatter-gather 并行 + Synthesizer 聚合 |
| **GraphStrategy** | 基于 DAG 的自定义工作流执行引擎 |
| **DebateStrategy** | 多轮辩论达成共识 |
| **HandoffStrategy** | 动态控制权移交，首个完成者胜出 |
| **TeamOrchestrator** | 团队运行时，负责选策略 + 按需注入共享内存 + 转发执行 |
| **Supervisor** | 本质是 BaseAgent，专责任务拆解与路由，不做编排决策 |
| **OrchestrationContext** | 编排策略的运行时上下文，由 TeamOrchestrator 构造并传给策略 |
| **Synthesizer** | MoA 聚合器，将多个并行候选结果合成为最终结果（ConcatSynthesizer / LLMSynthesizer / BestOfSynthesizer） |

## 传输与互操作

| 术语 | 定义 |
|---|---|
| **AgentTransport** | Agent 间通信协议，含 send_task / poll_status / receive_result |
| **TransportRegistry** | 按 protocol_name 路由的传输注册表 |
| **InternalTransport** | 进程内传输，基于 asyncio.create_task |
| **A2ATransport** | Google A2A 协议传输 |
| **MCPTransport** | Model Context Protocol 传输 |
| **DelegationSpec** | 委派规格 DTO，含 protocol（internal / a2a / mcp）、目标 Agent 标识、子任务等 |

## 决策与结果

| 术语 | 定义 |
|---|---|
| **StructuredDecision** | 结构化决策 DTO，含 action_type、tool_calls、delegate_to 等 |
| **Observation** | 执行观察 DTO，含 success、payload、error 等 |
| **Reflection** | 反思 DTO，含 verdict（on_track / needs_correction / blocked） |
| **Result** | 运行结果 DTO，含 status、output、budget_used 等 |
| **TypedState** | 运行时状态 DTO，含 working_memory、budget、checkpoints 等 |

## 命名约定

| 术语 | 定义 |
|---|---|
| **Simple 前缀** | `Simple<ProtocolName>` 表示该 Protocol 的最小可行参考实现，允许简化算法，docstring 首行须声明"最小实现："+ 能力边界（ADR-0011） |
| **PromptManager** | 唯一豁免的"Manager"命名——Prompt 模板的注册与渲染在 Agent 领域缺少更精确的领域词（glossary 显式豁免） |

## 图执行

| 术语 | 定义 |
|---|---|
| **ExecutionGraph** | DAG 工作流定义，含节点（entry/exit/agent/router/aggregator）和边（fixed/conditional/parallel） |
| **GraphNode** | 图节点 DTO |
| **GraphEdge** | 图边 DTO，支持条件函数 |
| **GroupChat** | 基于 ExecutionGraph 的全连接 mesh 预置模板 |

## 基础设施

| 术语 | 定义 |
|---|---|
| **ComponentRegistry** | 分类 + 名称的 DI 注册表 |
| **NamedRegistry** | 按名称注册的泛型基类 |
| **StrategyRegistry** | BrainStrategy 工厂注册表 |
| **OrchestrationStrategyRegistry** | 编排策略工厂注册表 |
| **SkillRouter** | 运行时动态选择 Prompt 模板 / 工具子集 |
| **EventBus** | 事件发布-订阅协议 |
| **StateStore** | 状态持久化协议 |
| **Budget** | 预算控制 DTO，含 token / cost / step / wall-clock 上限 |
