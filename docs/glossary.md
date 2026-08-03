# 术语表（渐进披露）

## L-User

| 术语 | 定义 |
|---|---|
| **Agent** | L4 门面：角色 + 工具 + LLM，`await agent.run(task)` |
| **MultiAgentTeam** | L4 团队门面：`members` + `TeamProcess`，`await team.run(objective)` |
| **TeamProcess** | 族内拓扑：hierarchical / sequential / parallel / graph / debate / handoff / swarm |
| **OrchestrationFamily** | 控制权归属族：supervisor / choreography / peer / graph（ADR-0027） |
| **multi-delegate** | 一步并行委派多个角色（`delegate_targets` + `DelegateOperation` gather） |
| **RoutingState** | SUPERVISOR 自由 PM 控制面（无全员结算）；与 ConsultationState 隔离 |
| **PeerStrategy** | PEER 族：handoff（首成即返）/ swarm（轮询累积） |
| **Result** | 运行最终结果：status / output / budget / error |
| **run** | 全链路唯一生命周期动词（Agent / Team / CognitiveLoop） |

## L-Team

| 术语 | 定义 |
|---|---|
| **CognitiveAgent** | L3 可调度单元：CognitiveLoop + RoleProfile（原 SimpleAgent / BaseAgent） |
| **TeamOrchestrator** / **Supervisor** | 组团队、注入共享记忆、绑定主管、选择 process 策略 |
| **TeamProcessStrategy** | 某一种 TeamProcess 的实现 |
| **TeamContext** | 策略运行时上下文（原 OrchestrationContext） |
| **TeamUnit** | 团队入口协议（原 TeamEntrypoint） |
| **AgentUnit** | 单体入口协议（原 AgentEntrypoint） |
| **teammates_text** | 写进提示词的「队友是谁」（由 `build_teammates_text` 从 ConsultationState.teammates 渲染） |
| **ConsultationState** / **HierarchicalConsultation** | SUPERVISOR·consultation 控制面（board / teammates / retry）；字段白名单锁定；solo/member 为 None |
| **SupervisorPlane** | SUPERVISOR 控制面种类：consultation（已实现）/ routing（预留） |
| **DecisionGate**（配置） | 结算强度：默认 `none`（自由经理）；`must_consult_all` 为咨询合规 opt-in |
| **SupervisorBinder** | 组装期绑定 channel + gate + supervisor cognition；失败显式抛 `SupervisorBindError` |
| **MemberStatus** | 必问成员是否已咨询完毕（原 DelegationLedger / team_progress） |
| **InMemoryMemberStatus** | MemberStatus 默认不可变实现 |
| **AgentChannel** / **AgentTransport** | 成员间任务通道；内置 Internal / A2A / MCP Transport |
| **SharedMemory** / **SharedMemoryStore** / **TeamSharedMemory** | 团队共享记忆 |
| **SharedMemoryTool** | 将共享记忆包装为普通 Tool |
| **DecisionGate**（组件） | 决策出/入门硬规则（`enforce` 必选出门校验，`SupportsShortcut` 可选入门快速路径） |
| **SupportsShortcut** | 可选能力：DecisionGate 在 LLM 之前提供确定性快速路径（`try_shortcut`） |
| **MustConsultAllMembers** | 未咨询完所有必需角色时禁止 respond（原 RosterCoverage） |
| **RunContext** | 一次 `run` 的调用元数据（trace_id / from_role / deadline；可选 consultation） |
| **SupervisorReasoner** | hierarchical supervisor 专用 Reasoner（hierarchical_prompt + consultation）；组装期绑定 |
| **TeamConfig** / **RoleProfile** | 团队配置 / 角色画像 |
| **TeamMessage** / **TeamAssignment** | 跨 Agent 消息 / 分工单元 |

## L-Loop

| 术语 | 定义 |
|---|---|
| **L0–L4** | 框架五层：基础设施 / 认知组件 / 认知运行时 / Agent 抽象 / 应用编排 |
| **CognitiveLoop** / **CognitiveRuntime** | perceive → think → act → reflect → stop 认知闭环 |
| **AgentState** | 循环状态容器（原 TypedState） |
| **Decision** | 一步行动决策（原 StructuredDecision） |
| **Observation** | 行动结果（原 ActResult 类型名；字段仍可 success/payload） |
| **Reflection** | 自省判定 |
| **StopRule** / **StopDecision** / **StopReason** | 是否结束循环（合并原 LoopJudge / TerminationSignal / StepOutcome 对外双轨） |
| **DefaultStopRule** | 默认终止裁判；内部可组合 StopOutcomePolicy |
| **StopOutcome** / **StopOutcomePolicy** / **DefaultStopOutcomePolicy** | 单步结果判定（DefaultStopRule 内部使用） |
| **Brain** / **Body** / **Memory** | 想 / 做 / 记（Brain 原 BrainStrategy） |
| **ModularBrain** / **MAP** | 默认 Brain；CandidateEvaluationPipeline 做 decompose → evaluate |
| **Turn** | 单步记录：decision + act result + reflection |
| **Budget** | token / cost / steps / wall_clock 预算 |
| **Hook** / **HookRegistry** / **EventBus** / **Event** | 生命周期钩子与事件 |
| **Observability** / **TraceSpan** / **ConsoleObservability** / **JSONL** | 可观测性 |
| **StateStore** / **StateSnapshot** | 状态持久化与快照 |

## L-Plugin / L0

| 术语 | 定义 |
|---|---|
| **Reasoner** / **Critic** / **DecisionParser** | 候选生成 / 自省 / 解析 |
| **Action** / **ActionRegistry** / **ActionOperation** | 行动能力与路由 |
| **Respond** / **UseTool** / **Delegate** / **Handoff** / **Operation** | 内置行动 |
| **ToolRunner** / **SafeExecutor** | 权限 + 重试 + 缓存后执行工具 |
| **ToolRegistry** / **Tool** / **ToolPermissionManifest** | 工具注册与权限 |
| **RetryPolicy** / **CacheConfig** | 重试与缓存配置 |
| **BrainFactory** / **SimpleBrainFactory** | Brain 工厂（注册表用 NamedRegistry） |
| **MergeResults** / **Synthesizer** / **ConcatSynthesizer** | 并行结果聚合 |
| **LLMAdapter** / **Anthropic** / **OpenAI** / **Mock** / **Adapter** | 多厂商 LLM 适配 |
| **Transport** / **TransportRegistry** / **InternalTransport** / **A2ATransport** / **MCPTransport** | 传输实现与注册 |
| **ComponentRegistry** / **NamedRegistry** | DI / 按名注册表 |
| **Registries** | 三个发现型注册表的值对象包（components / brain_factories / orchestration），Assembly 私有持有，替代进程级全局单例（ADR-0024） |
| **Assembly** | 组合根的显式对象化版本，持有一份 Registries；`assemble_agent` / `assemble_team` 是其方法（原模块级自由函数） |
| **PromptManager** / **SkillRouter** | Prompt 模板与技能路由 |
| **FallbackPolicy** / **FallbackActionPolicy** | 未知 action 降级 |
| **DelegationSpec** / **AgentCard** / **TaskStatus** | 委派规格 / 能力名片 / 任务状态机 |
| **ApprovalPendingError** / **BudgetExceededError** / **ToolExecutionError** | 运行时异常 |
| **MemoryRecord** / **MemoryLayer** / **SkillRecord** / **KGTriple** | 记忆契约 |
| **ExecutionGraph** / **GraphNode** / **GraphEdge** / **GraphStrategy** | 图编排 |
| **CoALA** | 记忆分类参考：working / semantic / episodic / procedural |
| **ParallelStrategy** | 并行 TeamProcess 策略 |
| **SequentialStrategy** | 顺序 TeamProcess 策略 |
| **HierarchicalStrategy** | 主管委派 TeamProcess 策略 |
| **DebateStrategy** | 辩论 TeamProcess 策略 |
| **HandoffStrategy** | 交接 TeamProcess 策略 |
| **SimpleBody** | Body 默认实现 |
| **SimpleMemorySystem** | MemorySystem 默认实现 |
| **SimpleReasoner** | Reasoner 默认实现（team-agnostic，solo/member） |
| **SupervisorReasoner** | hierarchical supervisor 专用 Reasoner |
| **SimpleCritic** | Critic 默认实现 |
| **SimpleDecisionParser** | DecisionParser 默认实现 |
| **SimplePromptManager** | PromptManager 默认实现 |
| **SimpleEventBus** | EventBus 默认实现 |
| **SimpleHookRegistry** | HookRegistry 默认实现 |
| **SimpleSafeExecutor** | SafeExecutor / ToolRunner 默认实现 |
| **SimpleToolRegistry** | ToolRegistry 默认实现 |
| **ConcatSynthesizer** | Synthesizer 默认拼接实现 |
| **DelegateOperation** | delegate 行动实现 |
| **HandoffOperation** | handoff 行动实现 |
| **RespondOperation** | respond 行动实现 |
| **UseToolOperation** | use_tool 行动实现 |
| **CandidateEvaluationPipeline** | 候选评估管线协议（默认逻辑内联在 ModularBrain） |
| **KeywordSkillRouter** | SkillRouter 关键词实现 |
| **FallbackDecoratedBody** | 带降级策略的 Body 装饰器 |
| **OpenAICompatLLM** | OpenAI 兼容 LLMAdapter |
| **InMemoryStateStore** | StateStore 内存实现 |
| **JSONLFileObservability** | JSONL 文件 Observability |
| **CalculatorTool** / **WeatherTool** | 内置示例 Tool |

## 已废弃主名（仅允许过渡别名，见 contracts 内注释）

| 旧名 | 新名 |
|---|---|
| StructuredDecision | Decision |
| TypedState | AgentState |
| ActResult | Observation |
| DelegationLedger / team_progress | MemberStatus / member_status |
| roster / roster_desc | teammates_text |
| AgentEntrypoint / TeamEntrypoint | AgentUnit / TeamUnit |
| SimpleAgent / BaseAgent | CognitiveAgent |
| assemble_base_agent | assemble_agent |
| execute（Agent 入口） | run |
| CompletionPolicy / RosterCoverage | DecisionGate / MustConsultAllMembers |
| LoopJudge / TerminationSignal（对外） | StopRule / StopDecision |
| BrainStrategy | Brain |

## 禁止复活

除上述废弃名外，以下设计模式同样禁止重新引入：

- 双重公开 stop 类型（对外只保留 `StopRule` / `StopDecision` 单通道）
- Agent 入口签名带 `**context: str`（用 `RunContext` 类型化上下文替代）
- progress-text 字段 + 注入 hook 三件套（用 `MemberStatus` 替代）
