# 术语表

| 术语 | 定义 |
|---|---|
| **L0–L4** | 框架五层：基础设施层 / 认知组件层 / 认知运行时层 / Agent 抽象层 / 应用编排层 |
| **MAP** | ModularBrain 内候选评估管线：CandidateEvaluationPipeline 封装 decompose → evaluate（内含 predict / score / conflict check / arbitrate） |
| **认知闭环** | perceive → think → act → observe → reflect → update，框架核心循环 |
| **StructuredDecision** | Brain 输出的强类型决策对象，含 action_type / tool_call / delegate_to / rationale |
| **TypedState** | 贯穿运行时的强类型状态对象，携带 Budget、Checkpoint、记忆上下文 |
| **BrainStrategy** | 可插拔推理策略协议（ReAct / Plan-Execute / ToT 等），注册到 StrategyRegistry |
| **CognitiveRuntime** | L2 核心循环实现，驱动 perceive→think→act→reflect 每一步并触发 Hook |
| **Body** | L1 执行器组件，封装 ToolRegistry + SafeExecutor，对外暴露 act() |
| **SafeExecutor** | Body 内工具执行器，依次做权限校验 → 缓存命中 → 重试退避 → 沙箱执行 |
| **ToolPermissionManifest** | 每个角色声明的允许工具子集与调用频次上限 |
| **RetryPolicy / CacheConfig** | 工具执行的重试退避策略与缓存配置 |
| **AgentTransport** | 跨 Agent 通信协议适配器接口，内置 internal / a2a / mcp 三种实现 |
| **LLMAdapter** | L0 多厂商 LLM 统一调用接口，屏蔽 API 差异（含 Anthropic / OpenAI / Mock 实现） |
| **AgentCard** | Agent 对外发布的能力名片（角色、工具、协议、端点），用于 A2A 发现与委派 |
| **TaskStatus** | 任务生命周期状态机：submitted → working → input-required / completed / failed / canceled |
| **DelegationSpec** | 委派契约，含目标角色/Agent、子任务描述、协议选择（internal / a2a / mcp） |
| **ApprovalPendingError** | pre_act Hook 判定高风险操作时抛出，Runtime 挂起等待人工审批后 resume |
| **MemoryLayer** | 单一记忆层协议（Working / Semantic / Episodic / Procedural / KnowledgeGraph） |
| **MemoryRecord / SkillRecord / KGTriple** | 记忆存储契约：通用记录 / 程序性技能记录 / 知识图谱三元组 |
| **HookRegistry** | 生命周期钩子注册表，支持 pre/post_perceive/think/act/reflect 及 on_start/error/complete |
| **EventBus / Event** | 异步事件广播机制，驱动跨组件松耦合通信与可观测性埋点 |
| **Observability / TraceSpan** | 可观测性接口与最小追踪单元，默认 Console 实现，可选 JSONL 文件落盘 |
| **PromptManager** | Prompt 模板集中管理与版本化渲染 |
| **Reasoner / Critic** | Brain 内候选思路生成器（调 LLM）与事后自省纠偏器 |
| **Reflection / Observation** | 反思结果（on_track / needs_correction / blocked）与工具执行观测结果 |
| **Result** | Runtime 最终输出契约，含 status / output / lessons / budget_used / trace |
| **RoleProfile / TeamConfig** | 角色设定契约（role/goal/backstory/tool 权限）与团队编排契约（process 类型/共享记忆层） |
| **SimpleAgent** | L3 单 Agent 运行时封装，``AgentEntrypoint`` 的默认实现（原 ``BaseAgent``）；持有 Runtime + RoleProfile + 预算字段 |
| **Agent** | L4 开发者门面：薄包装 ``assemble_base_agent``，对外暴露 ``run(task)`` |
| **MultiAgentTeam** | L4 团队门面：组合多个 ``Agent`` 成员，委托 ``assemble_team`` 构建 ``TeamOrchestrator`` |
| **TeamOrchestrator / Supervisor** | 团队编排器（hierarchical/sequential/graph/debate）与单向上委派汇总角色 |
| **TeamEntrypoint / TeamMessage** | 团队级运行时与跨 Agent 消息契约 |
| **Budget** | 多维度预算控制对象（token / cost / steps / wall_clock），超限触发 BudgetExceededError |
| **SkillRouter** | 技能路由协议，按 trigger_pattern 匹配任务并召回对应 SkillRecord |
| **Synthesizer** | 将多步结果合成为最终输出的组件 |
| **ExecutionGraph / GraphNode / GraphEdge** | 图编排策略的节点/边定义，支持条件分支与循环 |
| **OrchestrationContext** | 编排过程中传递的上下文对象 |
| **CoALA** | 语言智能体记忆分类参考框架：工作记忆 / 语义记忆 / 情景记忆 / 程序性记忆 |
| **ActionOperation** | 单一 action_type 的可插拔操作协议（原 ActionHandler），Strategy 模式落地 |
| **FallbackPolicy** | 未知 action_type 的降级策略协议（原 FallbackHandler） |
| **NamedRegistryProtocol** | 按名称注册/解析实体的通用注册表协议 |
| **Turn** | 单步认知闭环记录：decision + observation + reflection |
| **TeamAssignment** | 团队级分工单元，与单体内部计划项语义分离 |
| **SharedMemoryTool** | 将 SharedMemoryStore 包装为普通 Tool，成员经 use_tool 访问共享层 |
| **StepOutcome / StepOutcomePolicy** | 单步结果判定信号与策略，Loop 只消费 should_stop / final_output |
| **ComponentRegistry** | L0 按 (category, name) 注册组件实现的 DI 注册表 |
| **Respond / UseTool / Delegate / Handoff** | 内置 action_type 及对应 ActionOperation 实现 |
| **Operation** | 行动能力实现的命名后缀（替代 Handler），表示无状态策略对象 |
