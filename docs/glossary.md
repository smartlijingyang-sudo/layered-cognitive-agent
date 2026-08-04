# 术语表（渐进披露）

> 本表与代码由测试双向守护（`tests/test_code_conventions.py`）：
> 现役区的 CamelCase 术语必须对应 `lca` 包内真实类名（反向校验），
> 源码核心类的词根必须能在本表找到匹配（正向校验）。
> 被删除/改名的概念一律移入「已废弃主名」表，禁止滞留在现役区。

## L-User

团队协作只有一套模型（ADR-0030）：`Team = members + (lead XOR coordination)`。
常用路径是 lead（board/routing）与 `Pipeline` / `FanOut`；
PeerRelay / PeerSwarm / Debate / Graph 为进阶机制。

| 术语 | 定义 |
|---|---|
| **Agent** | L4 门面：角色 + 工具 + LLM，`await agent.run(task)` |
| **Team** | L4 团队门面：`members` + 恰好一种协作机制（`lead` XOR `coordination`），`await team.run(objective)` |
| **TeamLead** | 有主导者团队的入口：`TeamLead.routing/consult/board(agent)`，携带 LeadMandate |
| **LeadMandate** | 主导者授权：routing（自由 PM）/ consult（按需咨询）/ board（全员咨询后收口） |
| **Coordination** | 无主导者协作机制的联合类型（类型别名）：Pipeline / FanOut / PeerRelay / PeerSwarm / Debate / Graph |
| **Pipeline** | 协调机制（常用）：成员按序接力，前者产出进入后者上下文（策略键 `pipeline` → SequentialStrategy） |
| **FanOut** | 协调机制（常用）：全员并行后由 Synthesizer 归并（策略键 `fan_out` → ParallelStrategy） |
| **PeerRelay** | 协调机制（进阶）：成员间交接，首成即返（策略键 `peer_relay` → HandoffStrategy） |
| **PeerSwarm** | 协调机制（进阶）：轮询累积直至轮数上限（策略键 `peer_swarm` → SwarmStrategy） |
| **Debate** | 协调机制（进阶）：多轮辩论收敛（策略键 `debate` → DebateStrategy） |
| **Graph** | 协调机制（进阶）：按 ExecutionGraph 拓扑执行（策略键 `graph` → GraphStrategy） |
| **AgentComposer** / **TeamComposer** | 组合根：封闭组装 Agent / Team 对象图，无构造后 bind/install（ADR-0030） |
| **multi-delegate** | 一步并行委派多个角色（`Decision.delegations` 多条 + DelegateOperation gather） |
| **RoutingState** | lead·routing 授权下的主导者会话状态（无全员结算不变量）；与 ConsultationState 严格隔离，不得反向生长 |
| **Result** | 运行最终结果：status / output / budget / error |
| **run** | 全链路唯一生命周期动词（Agent / Team / CognitiveRuntime） |

## L-Team

| 术语 | 定义 |
|---|---|
| **Registries** | 三个发现型注册表的值对象包（components / brain_factories / orchestration），由 TeamComposer 私有持有，替代进程级全局单例 |
| **CognitiveAgent** | L3 可调度单元：CognitiveRuntime + RoleProfile |
| **TeamOrchestrator** | 组团队、注入共享记忆、绑定 lead、按策略键解析 TeamStrategy |
| **TeamStrategy** | 团队协作策略协议；每种 coordination / lead 路径一个实现类 |
| **TeamStrategyRegistry** | TeamStrategy 的 NamedRegistry（策略键 → 工厂） |
| **TeamContext** | 策略运行时上下文（含 transport / member_status / shared_memory） |
| **TeamUnit** | 团队入口协议 |
| **AgentUnit** | 单体入口协议 |
| **ConsultationState** | lead·consult/board 授权的会话状态（board / teammates / retry）；字段白名单锁定；solo/member 为 None；routing 语义不得长在这里 |
| **teammates_text** | 写进提示词的「队友是谁」（由 `build_teammates_text` 从 ConsultationState.teammates 渲染） |
| **DecisionGate**（配置） | 结算强度：由 LeadMandate 展开——routing → `none`（自由经理），board → `must_consult_all`（咨询合规） |
| **DecisionGate**（组件） | 决策出/入门硬规则（`enforce` 必选出门校验，`SupportsShortcut` 可选入门快速路径） |
| **SupportsShortcut** | 可选能力：DecisionGate 在 LLM 之前提供确定性快速路径（`try_shortcut`） |
| **MustConsultAllMembers** | 未咨询完所有必需角色时禁止 respond |
| **MemberStatus** | 必问成员是否已咨询完毕的 board |
| **InMemoryMemberStatus** | MemberStatus 默认不可变实现 |
| **AgentTransport** / **send_and_wait** | 成员间任务通道与统一调用端口；内置 Internal / A2A / MCP |
| **SharedMemoryStore** / **TeamSharedMemoryStore** | 共享记忆存储协议 / 团队按 MemoryLayer 分层的默认实现 |
| **RunContext** | 一次 `run` 的调用元数据（trace_id / from_role / deadline；可选 consultation） |
| **SupervisorReasoner** | lead 专用 Reasoner（lead 提示词 + consultation）；组装期由 TeamComposer 绑定 |
| **LeadBudgetPolicy** | lead 预算提升策略（compose_as_lead 时经 ComponentRegistry 解析） |
| **TeamConfig** / **RoleProfile** | 团队配置 / 角色画像 |
| **TeamMessage** / **TeamAssignment** | 跨 Agent 消息 / 分工单元 |

## L-Loop

| 术语 | 定义 |
|---|---|
| **L0–L4** | 框架五层：基础设施 / 认知组件 / 认知运行时 / Agent 抽象 / 应用编排 |
| **CognitiveRuntime** | 认知闭环 perceive → think → act → reflect → stop 的承载者（「CognitiveLoop」是该模式的概念名，不是类） |
| **AgentState** | 循环状态容器 |
| **Decision** | 一步行动决策；委派目标仅存于 `delegations` |
| **Observation** | 行动结果 |
| **Reflection** | 自省判定 |
| **StopRule** / **StopDecision** / **StopReason** | 是否结束循环 |
| **DefaultStopRule** | 默认终止裁判（``default_stop_rule.py``）；内部可组合 StopOutcomePolicy |
| **StopOutcome** / **StopOutcomePolicy** / **DefaultStopOutcomePolicy** | 单步结果判定（DefaultStopRule 内部使用） |
| **Brain** / **Body** / **MemorySystem** | 想 / 做 / 记 |
| **ModularBrain** | 默认 Brain（reasoner / critic / decision_parser 可替换）；CandidateEvaluationPipeline 做 decompose → evaluate |
| **Turn** | 单步记录：decision + act result + reflection |
| **Budget** | token / cost / steps / wall_clock 预算 |
| **Hook** / **HookRegistry** / **EventBus** / **Event** | 生命周期钩子与事件 |
| **Observability** / **TraceSpan** / **ConsoleObservability** / **JSONLFileObservability** | 可观测性（console 打印 / JSONL 落盘） |
| **StateStore** / **StateSnapshot** | 状态持久化与快照 |

## L-Plugin / L0

| 术语 | 定义 |
|---|---|
| **Reasoner** / **Critic** / **DecisionParser** | 候选生成 / 自省 / 解析 |
| **Action** / **ActionRegistry** / **ActionType** | 行动能力与路由（内置行动类型：respond / use_tool / delegate / handoff / stop / ask_human） |
| **RespondOperation** / **UseToolOperation** / **DelegateOperation** / **HandoffOperation** | 内置行动实现（delegate/handoff 行动 ≠ PeerRelay 协调机制） |
| **SafeExecutor** | 权限 + 重试 + 缓存后执行工具 |
| **ToolRegistry** / **Tool** / **ToolPermissionManifest** | 工具注册与权限 |
| **RetryPolicy** / **CacheConfig** | 重试与缓存配置 |
| **BrainFactory** / **SimpleBrainFactory** | Brain 工厂（注册表用 NamedRegistry） |
| **Synthesizer** / **ConcatSynthesizer** | 并行结果聚合协议 / 默认拼接实现 |
| **LLMAdapter** / **OpenAICompatAdapter** / **MockLLMAdapter** / **TelemetryLLMAdapter** | 多厂商 LLM 适配协议与实现（Telemetry 为装饰器） |
| **AgentTransport** / **TransportRegistry** / **InternalTransport** / **A2ATransport** / **MCPTransport** | 传输协议、注册与实现 |
| **ComponentRegistry** / **NamedRegistry** | DI / 按名注册表（ComponentRegistry 是 category → NamedRegistry 的组合器） |
| **RegistryKeyError** | 注册表硬查询失败异常（继承 ValueError） |
| **team_wiring** / **build_team_transport** | L4 团队 channel 接线（与 agent 组装决策分离） |
| **SkillRouter** / **KeywordSkillRouter** / **StaticSkillRouter** | 运行时动态选择 Prompt 模板 / 工具子集（关键词 / 静态映射） |
| **load_builtin_prompt** | 从 ``brain/prompts/*.md`` 加载内置模板 |
| **DegradationPolicy** / **GracefulDegradation** | 越界 action 优雅降级（防腐层归一化：解析期改写为词表内等价行动，经 Decision.degraded_from 溯源） |
| **DelegationSpec** / **AgentCard** / **TaskStatus** | 委派规格 / 能力名片 / 任务状态机 |
| **ApprovalPendingError** / **BudgetExceededError** / **ToolExecutionError** | 运行时异常 |
| **MemoryRecord** / **MemoryLayer** | 记忆契约（分层参考 CoALA：working / semantic / episodic / procedural） |
| **ExecutionGraph** / **GraphNode** / **GraphEdge** / **GraphStrategy** | 图编排 |
| **LeadStrategy** | lead 路径的 TeamStrategy（策略键 `lead`） |
| **ParallelStrategy** | FanOut 协调的 TeamStrategy（策略键 `fan_out`） |
| **SequentialStrategy** | Pipeline 协调的 TeamStrategy（策略键 `pipeline`） |
| **DebateStrategy** | Debate 协调的 TeamStrategy（策略键 `debate`） |
| **HandoffStrategy** | PeerRelay 协调的 TeamStrategy（策略键 `peer_relay`） |
| **SwarmStrategy** | PeerSwarm 协调的 TeamStrategy（策略键 `peer_swarm`） |
| **SimpleBody** | Body 默认实现 |
| **SimpleMemorySystem** | MemorySystem 默认实现 |
| **SimpleReasoner** | Reasoner 默认实现（team-agnostic，solo/member） |
| **SimpleCritic** | Critic 默认实现 |
| **SimpleDecisionParser** | DecisionParser 默认实现 |
| **SimpleEventBus** | EventBus 默认实现 |
| **SimpleHookRegistry** | HookRegistry 默认实现 |
| **SimpleSafeExecutor** | SafeExecutor 默认实现 |
| **SimpleToolRegistry** | ToolRegistry 默认实现 |
| **CandidateEvaluationPipeline** | 候选评估管线协议（SimpleCandidateEvaluationPipeline 为默认实现） |
| **InMemoryStateStore** | StateStore 内存实现 |
| **CalculatorTool** / **WeatherTool** | 内置示例 Tool |

## 已废弃主名（仅允许过渡别名，见 contracts 内注释）

| 旧名 | 新名 |
|---|---|
| MultiAgentTeam | Team |
| TeamProcess | LeadMandate + Coordination（一元的 lead XOR coordination，ADR-0030） |
| OrchestrationFamily / SupervisorMode / Recipe | 已删除，无替代概念（ADR-0030） |
| Assembly / assemble_agent | AgentComposer / TeamComposer |
| TeamProcessStrategy | TeamStrategy |
| HierarchicalStrategy | LeadStrategy |
| SupervisorPlane | 已删除；会话语义分裂为 RoutingState（routing）与 ConsultationState（consult/board） |
| SupervisorBinder | 已删除；绑定逻辑并入 TeamComposer.compose_as_lead |
| OpenAICompatLLM | OpenAICompatAdapter |
| SharedMemoryTool / SkillRecord / KGTriple | 已删除（共享记忆经 SharedMemoryStore；记忆契约收敛为 MemoryRecord） |
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
| judge（CognitiveRuntime 参数/字段） | stop_rule |
| default_loop_judge.py | default_stop_rule.py |
| brain_strategy（Agent/Assembly 参数） | brain |
| BrainStrategy | Brain |
| PromptManager / SimplePromptManager | Reasoner 内建模板字典（已溶解） |
| member_status/policy.py | member_status/required_action.py |
| FallbackPolicy / FallbackActionPolicy / FallbackDecoratedBody | DegradationPolicy / GracefulDegradation（降级前移至防腐层解析期，Body 不再承载异常驱动的降级装饰） |

## 禁止复活

除上述废弃名外，以下设计模式同样禁止重新引入：

- 三维旋钮（Family / Plane / Mode）与 Recipe / TeamProcess 公共面（ADR-0030）
- 双重公开 stop 类型（对外只保留 `StopRule` / `StopDecision` 单通道）
- Agent 入口签名带 `**context: str`（用 `RunContext` 类型化上下文替代）
- progress-text 字段 + 注入 hook 三件套（用 `MemberStatus` 替代）
